import json
import logging
import os
import sys
import time

import requests


def load_env_file(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


load_env_file()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ---- 감시 대상 ----
CO_CD = "A420"  # CGV 회사코드
SITE_NO = "0257"  # 광교 CGV 극장코드
MOV_NO = "30001323"  # 오디세이 영화코드
TARGET_DATE = "20260809"  # 상영일자 [테스트용 임시값 - 원래 8/10]
RTCTL_SCOP_CD = "08"
SCREEN_KEYWORD = "IMAX"  # 상영관 필터 키워드

SCHEDULE_API_URL = "https://cgv.co.kr/api/v1/booking/searchSchByMov"
BOOKING_PAGE_URL = "https://cgv.co.kr/cnm/movieBook/movie"
STATE_FILE = "notified_state.json"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "30"))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": BOOKING_PAGE_URL,
}


def fetch_schedules() -> list[dict]:
    params = {
        "coCd": CO_CD,
        "siteNo": SITE_NO,
        "scnYmd": TARGET_DATE,
        "movNo": MOV_NO,
        "rtctlScopCd": RTCTL_SCOP_CD,
    }
    response = requests.get(SCHEDULE_API_URL, headers=HEADERS, params=params, timeout=10)
    response.raise_for_status()
    return response.json().get("data", [])


def is_target_screen(item: dict) -> bool:
    return SCREEN_KEYWORD in (item.get("scnsNm") or "") or SCREEN_KEYWORD in (item.get("movkndDsplNm") or "")


def format_message(item: dict) -> str:
    start_time = item["scnsrtTm"]
    time_str = f"{start_time[:2]}:{start_time[2:]}"
    return (
        "CGV 예매 오픈!\n"
        f"영화: {item['movNm']}\n"
        f"극장: {item['siteNm']}\n"
        f"상영관: {item['scnsNm']} ({item['movkndDsplNm']})\n"
        f"시간: {time_str}\n"
        f"잔여좌석: {item['frSeatCnt']}/{item['stcnt']}\n"
        f"예매: {BOOKING_PAGE_URL}"
    )


def send_telegram_message(text: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    response = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=10)
    response.raise_for_status()


def load_notified_keys() -> set:
    if not os.path.exists(STATE_FILE):
        return set()
    with open(STATE_FILE, encoding="utf-8") as f:
        return {tuple(key) for key in json.load(f)}


def save_notified_keys(keys: set) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(keys), f, ensure_ascii=False, indent=2)


def check_once(notified_keys: set) -> set:
    """스케줄을 한 번 확인하고, 새로 발견된 스케줄에 대해 알림을 보낸 뒤 갱신된 notified_keys를 반환한다."""
    schedules = fetch_schedules()
    targets = [item for item in schedules if is_target_screen(item)]

    if not targets:
        logger.info("아직 예매 미오픈 (전체 스케줄 %d건)", len(schedules))

    for item in targets:
        key = (item["scnsNo"], item["scnSseq"], item["scnsrtTm"])
        if key in notified_keys:
            continue
        notified_keys.add(key)
        message = format_message(item)
        logger.info("새 %s 스케줄 발견, 알림 전송: %s", SCREEN_KEYWORD, message.replace("\n", " | "))
        send_telegram_message(message)

    return notified_keys


def main() -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise SystemExit("TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 환경변수를 설정해주세요 (.env 참고)")

    run_once = "--once" in sys.argv
    notified_keys = load_notified_keys()

    if run_once:
        notified_keys = check_once(notified_keys)
        save_notified_keys(notified_keys)
        return

    logger.info(
        "감시 시작 - 영화: %s, 극장코드: %s, 날짜: %s, 상영관: %s, 주기: %d초",
        MOV_NO, SITE_NO, TARGET_DATE, SCREEN_KEYWORD, POLL_INTERVAL_SECONDS,
    )

    while True:
        try:
            notified_keys = check_once(notified_keys)
            save_notified_keys(notified_keys)
        except requests.RequestException as exc:
            logger.warning("요청 실패, %d초 후 재시도: %s", POLL_INTERVAL_SECONDS, exc)

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
