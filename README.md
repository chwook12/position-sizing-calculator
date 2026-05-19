# Position Sizing Calculator

종목명 또는 심볼로 가격을 불러와 포지션 수량, 포지션 사이즈, 리스크 금액을 계산하는 웹앱입니다.

## 로컬 실행

```powershell
python app.py
```

기본 주소:

```text
http://127.0.0.1:8000
```

## 한국투자 NXT 실시간 시세

한국투자증권 KIS Developers 앱키가 있으면 로컬/배포 환경에서 NXT 실시간 체결가를 우선 사용합니다. 설정이 없거나 장외/타임아웃이면 기존 Nextrade 20분 지연 데이터로 자동 전환됩니다.

방법 1: 환경 변수 사용

```powershell
$env:KIS_APP_KEY="발급받은_앱키"
$env:KIS_APP_SECRET="발급받은_앱시크릿"
$env:KIS_ENV="prod"
python app.py
```

방법 2: 로컬 설정 파일 사용

`kis_config.example.json`을 복사해 `kis_config.json`으로 만든 뒤 앱키를 입력하세요. `kis_config.json`은 `.gitignore`에 포함되어 있어 GitHub에 올리지 않는 용도입니다.

배포 환경에서는 `kis_config.json`을 올리지 말고 환경 변수만 사용하세요.

## 클라우드 배포

이 컴퓨터를 꺼도 모바일에서 접속하려면 Render, Railway, Fly.io 같은 클라우드 웹 서비스에 배포해야 합니다.

### Render 추천 설정

- Runtime: Python
- Build Command: `pip install -r requirements.txt`
- Start Command: `python app.py`
- Instance Type: 항상 켜두려면 유료 플랜 권장

### Render 환경 변수

Render 대시보드의 `Environment` 메뉴에서 아래 값을 추가하세요.

- `KIS_ENV`: `prod`
- `KIS_APP_KEY`: 한국투자 App Key
- `KIS_APP_SECRET`: 한국투자 App Secret
- `APP_USERNAME`: 접속 아이디, 예: `user`
- `APP_PASSWORD`: 접속 비밀번호

`APP_PASSWORD`를 설정하면 배포 주소 접속 시 브라우저 로그인 창이 뜹니다. 혼자 쓰는 개인 배포라면 설정을 권장합니다.

이 저장소에는 Render Blueprint용 `render.yaml`, 범용 `Procfile`, 컨테이너 배포용 `Dockerfile`이 포함되어 있습니다.

## 기능

- `삼성전자`, `애플`, `tesla` 같은 종목명 검색
- `005930`, `TSLA`, `AAPL` 같은 심볼 직접 입력
- KR, US, JP, HK, CN, VN 마켓 선택
- KR 종목은 진입가와 손절가 기준을 KRX/NXT로 각각 선택
- KRX 가격은 Naver/KRX 데이터, NXT 가격은 한국투자 실시간 데이터 또는 Nextrade 공식 지연 데이터 사용
- 해외 종목은 Yahoo Finance 차트 가격 사용
- 가격 로드 시 진입가와 방향별 기본 손절가 자동 입력
- RPT는 원화 기준으로 입력하고, 선택 통화에 맞게 환율 환산 후 수량 계산
- RPT 기준 수량, SL %, 포지션 사이즈, 리스크 금액 자동 계산
