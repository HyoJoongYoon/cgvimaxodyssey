# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

CGV 예매 오픈 알리미 챗봇. `main.py`가 CGV 상영 스케줄 API(`searchSchByMov`)를 주기적으로 폴링해서,
지정한 영화/극장/날짜/상영관 조건의 좌석 예매가 열리면 텔레그램으로 알림을 보낸다.

감시 대상은 `main.py` 상단 상수로 하드코딩되어 있다 (영화: 오디세이 / 극장: 광교 CGV / 상영관: IMAX / 날짜: 2026-08-10).
다른 영화·극장·날짜를 감시하려면 이 상수들을 바꾸면 된다 (`MOV_NO`, `SITE_NO`, `TARGET_DATE`, `SCREEN_KEYWORD`).

CGV 스케줄 API는 인증이 필요 없고, `Referer` 헤더만 있으면 응답한다 (2026-07-25 기준 확인됨).

## Setup

```
pip install -r requirements.txt
cp .env.example .env   # 그 다음 .env에 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 입력
```

텔레그램 봇 토큰: `@BotFather`에게 `/newbot` 전송 후 발급받은 토큰을 `TELEGRAM_BOT_TOKEN`에 입력.
채팅 ID: 만든 봇과 대화를 한 번 시작한 뒤 `https://api.telegram.org/bot<TOKEN>/getUpdates`를 브라우저로 열어서 `chat.id` 값을 확인.

## Running

로컬에서 계속 켜두는 방식:

```
python main.py
```

무한 루프로 계속 실행되며 (기본 30초 간격 폴링), 새로운 상영 스케줄을 감지할 때마다 텔레그램으로 알림을 보낸다.
중복 알림은 방지되며 (`notified_state.json`에 기록), 네트워크 오류가 나도 죽지 않고 재시도한다.

1회만 확인하고 종료하는 모드 (GitHub Actions 등 CI 환경용):

```
python main.py --once
```

## GitHub Actions로 무료 24시간 감시

`.github/workflows/cgv-alert.yml`이 5분 간격 cron으로 `python main.py --once`를 실행하고,
`notified_state.json`을 커밋해서 실행 간 중복 알림 상태를 유지한다.

설정 순서:
1. 이 저장소를 GitHub에 push
2. 저장소 Settings → Actions → General → Workflow permissions → **Read and write permissions** 체크 (상태 파일 커밋에 필요)
3. 저장소 Settings → Secrets and variables → Actions → New repository secret
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
4. Actions 탭에서 워크플로우를 수동 실행(`workflow_dispatch`)해서 정상 동작 확인

cron 최소 간격이 5분이고 GitHub 부하에 따라 실제 실행이 지연될 수 있어, 초 단위로 빠른 반응이 필요하면 로컬/서버에서 상시 실행하는 쪽이 낫다.

There is no build system, linter, or test framework set up yet. When those are added, update this file with the actual commands.
