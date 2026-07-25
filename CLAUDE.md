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

`.github/workflows/cgv-alert.yml`이 `workflow_dispatch`(수동/API 트리거)로 `python main.py --once`를 실행하고,
`notified_state.json`을 커밋해서 실행 간 중복 알림 상태를 유지한다.

GitHub의 자체 `schedule:` cron 트리거는 5분 간격으로 설정해도 실제로는 GitHub 서버 부하에 따라 수십 분씩 지연되는
경우가 많아서(공식 문서화된 제약) 사용하지 않는다. 대신 외부 무료 cron 서비스(cron-job.org)가 GitHub REST API의
`workflow_dispatch` 엔드포인트를 주기적으로 직접 호출해서 워크플로우를 트리거한다 — API 호출은 GitHub의 저우선순위
schedule 큐를 거치지 않아서 훨씬 정확한 시간에 실행된다.

설정 순서:
1. 이 저장소를 GitHub에 push
2. 저장소 Settings → Actions → General → Workflow permissions → **Read and write permissions** 체크 (상태 파일 커밋에 필요)
3. 저장소 Settings → Secrets and variables → Actions → New repository secret
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
4. GitHub에서 이 저장소의 Actions에 한정된 fine-grained PAT 발급 (Settings → Developer settings →
   Personal access tokens → Fine-grained tokens, 이 저장소만 선택, Actions 권한 Read and write)
5. [cron-job.org](https://cron-job.org)에 무료 가입 후 cron job 생성:
   - URL: `https://api.github.com/repos/HyoJoongYoon/cgvimaxodyssey/actions/workflows/cgv-alert.yml/dispatches`
   - Method: `POST`
   - Headers: `Accept: application/vnd.github+json`, `Authorization: Bearer <PAT>`, `X-GitHub-Api-Version: 2022-11-28`
   - Body: `{"ref":"master"}`
   - 실행 주기: 3~5분 (GitHub Actions 무료 분당 사용량 한도를 고려해서 너무 짧게 잡지 않는다)
6. Actions 탭에서 워크플로우를 수동 실행(`workflow_dispatch`)해서 정상 동작 확인, cron-job.org 실행 로그로 주기적 트리거 확인

GitHub Actions 무료 분(분당 청구) 한도를 넘지 않도록 cron 주기와 계정 Billing의 spending limit 설정을 확인해둔다.

There is no build system, linter, or test framework set up yet. When those are added, update this file with the actual commands.
