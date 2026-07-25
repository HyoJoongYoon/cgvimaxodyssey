# 작업 요약 (SESSION-SUMMARY)

CGV 예매 오픈 알리미 챗봇 구축 세션 정리. 2026-07-25 기준.

## 목표

영화 **오디세이**, **광교 CGV**, **IMAX**, 상영일 **2026-08-10** 좌석 예매가 열리는 순간을 감지해서 텔레그램으로 알림을 보낸다.

## 어떻게 동작하는가

1. CGV 내부 API(`GET https://cgv.co.kr/api/v1/booking/searchSchByMov`)를 주기적으로 호출한다.
   - 인증 불필요, `Referer: https://cgv.co.kr/cnm/movieBook/movie` 헤더만 있으면 응답함 (2026-07-25 확인).
   - 이 API는 CGV 사이트가 Next.js SPA라 정적 HTML 스크래핑이 불가능해서, 브라우저 DevTools 네트워크 탭으로 직접 캡처해서 알아냄.
2. 응답에서 `IMAX`가 포함된 상영관만 걸러서, 새로 나타난 스케줄이 있으면 텔레그램으로 메시지 전송.
3. 이미 알림 보낸 스케줄은 `notified_state.json`에 `(날짜, 상영관번호, 회차, 시작시간)` 키로 기록해서 중복 알림 방지.

## 파일 구성

- `main.py` — 감시 로직 본체. 상단 상수(`MOV_NO`, `SITE_NO`, `TARGET_DATE`, `SCREEN_KEYWORD`)로 감시 대상 지정.
- `requirements.txt` — `requests`만 사용 (개발 샌드박스에 pip가 없어서 `python-dotenv` 대신 `.env`를 직접 파싱하는 `load_env_file()`을 자체 구현).
- `.env` (gitignore 처리, 로컬 전용) — `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `POLL_INTERVAL_SECONDS` 보관.
- `.env.example` — `.env` 템플릿.
- `notified_state.json` — 알림 발송 이력 상태 파일. GitHub Actions가 실행마다 커밋해서 상태를 유지.
- `.github/workflows/cgv-alert.yml` — 5분 간격 cron으로 `python main.py --once` 실행 후 상태 파일 자동 커밋.

## 배포 방식: GitHub Actions

로컬 PC(WSL2)를 계속 켜둘 필요 없이 무료로 24시간 감시하기 위해 GitHub Actions로 이전.

- 저장소: `https://github.com/HyoJoongYoon/cgvimaxodyssey` (private)
- Settings → Actions → Workflow permissions → **Read and write** 활성화 (상태 파일 커밋용)
- Repository Secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- `schedule: cron: "*/5 * * * *"` + `workflow_dispatch`(수동 실행)로 트리거

## 검증한 내용

- 2026-08-09(테스트용 이미 열린 날짜)로 `TARGET_DATE`를 임시로 바꿔서 실제 텔레그램 알림이 오는지 end-to-end로 확인 → 정상 수신 확인 후 `20260810`으로 원복.
- 이 과정에서 dedup 키가 날짜를 포함하지 않아서, 8/9 테스트 기록이 8/10 실제 알림을 막을 수 있는 버그를 발견 → 키에 `scnYmd` 추가하고 `notified_state.json`을 `[]`로 초기화해서 해결.
- GitHub Actions "Scheduled" 실행이 실제로 도는 것을 Actions 탭에서 확인.

## 알려진 한계 (사용자가 현재 상태 유지로 결정함)

GitHub Actions의 `schedule` cron은 best-effort라 5분 간격으로 설정해도 실제로는 GitHub 서버 부하에 따라 수십 분까지 지연될 수 있음 (공식적으로 문서화된 제약). 대안으로 외부 cron 서비스(PAT로 `workflow_dispatch` 직접 호출) 또는 상시 켜진 무료 VM을 제안했으나, 사용자가 **현재 설정 그대로 유지**하기로 결정함. 지연이 문제가 되면 나중에 언제든 전환 가능.

## 현재 상태

- `TARGET_DATE = 20260810`로 실제 감시 중.
- `notified_state.json`은 빈 배열 `[]` (테스트 기록 정리 완료, 실제 알림만 쌓일 예정).
- 8/10 예매가 열리면 자동으로 텔레그램 알림이 온다. 추가 조치 불필요.
