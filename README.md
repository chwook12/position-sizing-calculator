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

## 클라우드 배포

이 컴퓨터를 꺼도 모바일에서 접속하려면 Render, Railway, Fly.io 같은 클라우드 웹 서비스에 배포해야 합니다.

### Render 추천 설정

- Runtime: Python
- Build Command: `pip install -r requirements.txt`
- Start Command: `python app.py`
- Instance Type: 항상 켜두려면 유료 플랜 권장

이 저장소에는 Render Blueprint용 `render.yaml`, 범용 `Procfile`, 컨테이너 배포용 `Dockerfile`이 포함되어 있습니다.

## 기능

- `삼성전자`, `애플`, `tesla` 같은 종목명 검색
- `005930`, `TSLA`, `AAPL` 같은 심볼 직접 입력
- KR, US, JP, HK, CN, VN 마켓 선택
- KR 종목은 진입가와 손절가 기준을 KRX/NXT로 각각 선택
- KRX 가격은 Naver/KRX 데이터, NXT 가격은 Nextrade 공식 정규시장 데이터 사용
- 해외 종목은 Yahoo Finance 차트 가격 사용
- 가격 로드 시 진입가와 방향별 기본 손절가 자동 입력
- RPT는 원화 기준으로 입력하고, 선택 통화에 맞게 환율 환산 후 수량 계산
- RPT 기준 수량, SL %, 포지션 사이즈, 리스크 금액 자동 계산
