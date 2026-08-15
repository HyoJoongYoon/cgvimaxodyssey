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

CO_CD = "A420"  # CGV 회사코드
RTCTL_SCOP_CD = "08"

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

# ---- 감시 대상 ----
# mode "booking_open": cntlYn(예매 통제 여부)이 N으로 바뀌는 순간(예매 준비중 -> 예매 오픈) 딱 한 번 알림
# mode "seat_threshold": 잔여좌석(frSeatCnt)이 min_free_seats 미만 -> 이상으로 바뀔 때마다(취소표 등으로 좌석이 늘어남) 알림
WATCHES = [
    {
        "name": "스파이더맨 8/23 예매오픈",
        "site_no": "0013",  # 용산아이파크몰 CGV
        "mov_no": "30001192",  # 스파이더맨-브랜드 뉴 데이
        "scn_ymd": "20260823",
        "screen_keyword": "PRIVATE BOX",  # SCREENX관(리클라이너) with PRIVATE BOX
        "mode": "booking_open",
    },
    {
        "name": "스파이더맨 8/16 20시 취소표",
        "site_no": "0013",  # 용산아이파크몰 CGV
        "mov_no": "30001192",  # 스파이더맨-브랜드 뉴 데이
        "scn_ymd": "20260816",
        "screen_keyword": "PRIVATE BOX",  # SCREENX관(리클라이너) with PRIVATE BOX
        "start_time": "2000",  # 20:00 회차만
        "mode": "seat_threshold",
        "min_free_seats": 4,  # 현재 장애인석 2석만 남은 상태 - 그 이상으로 늘어나면(일반석 추가 오픈) 알림
    },
]


def fetch_schedules(site_no: str, mov_no: str, scn_ymd: str) -> list[dict]:
    params = {
        "coCd": CO_CD,
        "siteNo": site_no,
        "scnYmd": scn_ymd,
        "movNo": mov_no,
        "rtctlScopCd": RTCTL_SCOP_CD,
    }
    response = requests.get(SCHEDULE_API_URL, headers=HEADERS, params=params, timeout=10)
    response.raise_for_status()
    return response.json().get("data", [])


def matches_watch(item: dict, watch: dict) -> bool:
    keyword = watch["screen_keyword"]
    if keyword not in (item.get("scnsNm") or "") and keyword not in (item.get("movkndDsplNm") or ""):
        return False
    start_time = watch.get("start_time")
    if start_time and item.get("scnsrtTm") != start_time:
        return False
    return True


def item_key(watch: dict, item: dict) -> str:
    return "|".join([watch["name"], item["scnYmd"], item["scnsNo"], item["scnSseq"], item["scnsrtTm"]])


def format_open_message(item: dict) -> str:
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


def format_seat_message(item: dict, min_free_seats: int) -> str:
    start_time = item["scnsrtTm"]
    time_str = f"{start_time[:2]}:{start_time[2:]}"
    return (
        f"CGV 좌석 {min_free_seats}석 이상 확보!\n"
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


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"notified": [], "seat_watch": {}}
    with open(STATE_FILE, encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, list):
        return {"notified": raw, "seat_watch": {}}
    raw.setdefault("notified", [])
    raw.setdefault("seat_watch", {})
    return raw


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)


def check_once(state: dict) -> dict:
    """감시 대상을 한 번씩 확인하고, 조건을 만족하는 새 항목에 대해 알림을 보낸 뒤 갱신된 state를 반환한다."""
    notified_keys = {tuple(key) for key in state["notified"]}
    seat_watch = state["seat_watch"]
    schedule_cache: dict[tuple[str, str, str], list[dict]] = {}

    for watch in WATCHES:
        cache_key = (watch["site_no"], watch["mov_no"], watch["scn_ymd"])
        if cache_key not in schedule_cache:
            schedule_cache[cache_key] = fetch_schedules(*cache_key)
        schedules = schedule_cache[cache_key]
        targets = [item for item in schedules if matches_watch(item, watch)]

        if not targets:
            logger.info("[%s] 조건에 맞는 스케줄 없음 (전체 %d건)", watch["name"], len(schedules))
            continue

        if watch["mode"] == "booking_open":
            for item in targets:
                if item.get("cntlYn") != "N":
                    continue
                key = (watch["name"], item["scnYmd"], item["scnsNo"], item["scnSseq"], item["scnsrtTm"])
                if key in notified_keys:
                    continue
                notified_keys.add(key)
                message = format_open_message(item)
                logger.info("[%s] 예매 오픈 감지, 알림 전송: %s", watch["name"], message.replace("\n", " | "))
                send_telegram_message(message)

        elif watch["mode"] == "seat_threshold":
            min_free_seats = watch["min_free_seats"]
            for item in targets:
                key = item_key(watch, item)
                free_seats = int(item.get("frSeatCnt") or 0)
                prev_free_seats = seat_watch.get(key, 0)
                if free_seats >= min_free_seats and prev_free_seats < min_free_seats:
                    message = format_seat_message(item, min_free_seats)
                    logger.info("[%s] 좌석 %d석 이상 감지, 알림 전송: %s", watch["name"], min_free_seats, message.replace("\n", " | "))
                    send_telegram_message(message)
                seat_watch[key] = free_seats

    state["notified"] = sorted(notified_keys)
    state["seat_watch"] = seat_watch
    return state


def main() -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise SystemExit("TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 환경변수를 설정해주세요 (.env 참고)")

    run_once = "--once" in sys.argv
    state = load_state()

    if run_once:
        state = check_once(state)
        save_state(state)
        return

    logger.info("감시 시작 - 대상 %d건, 주기: %d초", len(WATCHES), POLL_INTERVAL_SECONDS)
    for watch in WATCHES:
        logger.info("  - %s", watch["name"])

    while True:
        try:
            state = check_once(state)
            save_state(state)
        except requests.RequestException as exc:
            logger.warning("요청 실패, %d초 후 재시도: %s", POLL_INTERVAL_SECONDS, exc)

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
