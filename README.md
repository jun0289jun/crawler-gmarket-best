# G마켓 베스트 일일 크롤러

이 저장소는 **G마켓 베스트 페이지**에서 1위부터 200위까지의 상품 정보를 매일 수집하고, 생성된 CSV 파일을 이메일로 전송하도록 구성되어 있습니다. GitHub Actions 예약 실행은 한국시간 기준 매일 오전 9시에 맞춰 UTC 0시 cron으로 설정되어 있습니다.[1]

현재 크롤러는 GitHub Actions 서버 IP에서 Playwright 브라우저 접근이 차단될 수 있다는 점을 고려해 **`requests` 기반 HTML/Next.js 초기 데이터 확인을 먼저 시도**하고, 실패하면 **Playwright stealth 보완 + 시스템 Chrome/Chromium + Xvfb headed 실행**으로 fallback합니다.

> 최종가격 추출의 1순위 기준은 `.box__price-seller span.text.text__value`입니다. 렌더링 DOM을 사용할 수 있을 때는 동일 선택자 안에서 빨간색 `#DA120D` 가격을 최우선으로 사용하고, 빨간색 가격이 없으면 검정색 `#424242` 가격을 사용합니다. 브라우저 접근이 차단되어 Next.js 초기 데이터만 사용 가능한 경우에는 `discountPrice`를 빨간색 할인가의 대체값으로, 일반 `price`를 검정색 가격의 대체값으로 기록하며 `final_price_extraction_note`에 해당 경로를 남깁니다.

## 구성 파일

| 파일 | 역할 |
|---|---|
| `gmarket_best_crawler.py` | `requests` → Next 초기 데이터 → Playwright stealth fallback 순서로 G마켓 베스트 1~200위 상품을 CSV로 저장합니다. |
| `send_email.py` | 생성된 CSV 파일을 SMTP 이메일 첨부로 발송합니다. |
| `.github/workflows/gmarket-best-daily.yml` | 매일 KST 09:00, 즉 UTC 00:00에 크롤링과 이메일 발송을 실행합니다. |
| `requirements.txt` | Python 실행에 필요한 패키지를 정의합니다. |
| `.gitignore` | 로컬 실행 산출물과 민감 정보 파일이 커밋되지 않도록 제외합니다. |

## GitHub Actions 시크릿 설정

이메일 전송에는 SMTP 계정 정보가 필요합니다. GitHub 저장소의 **Settings → Secrets and variables → Actions → New repository secret** 메뉴에서 아래 값을 등록하세요. 비밀번호는 이메일 계정의 실제 비밀번호가 아니라, 가능하면 서비스에서 발급한 **앱 비밀번호 또는 SMTP 전용 비밀번호**를 사용하는 것이 안전합니다.

| Secret 이름 | 필수 여부 | 예시 | 설명 |
|---|---:|---|---|
| `SMTP_HOST` | 필수 | `smtp.naver.com` | SMTP 서버 주소입니다. |
| `SMTP_PORT` | 권장 | `587` | TLS 사용 시 일반적으로 587을 사용합니다. SSL 방식이면 보통 465를 사용합니다. |
| `SMTP_USERNAME` | 필수 | `your_id@naver.com` | SMTP 로그인 계정입니다. |
| `SMTP_PASSWORD` | 필수 | `********` | SMTP 로그인 비밀번호 또는 앱 비밀번호입니다. |
| `SMTP_FROM` | 선택 | `your_id@naver.com` | 발신자 주소입니다. 미설정 시 `SMTP_USERNAME`을 사용합니다. |
| `SMTP_TO` | 선택 | `dideum@naver.com` | 수신자 주소입니다. 미설정 시 `dideum@naver.com`으로 전송합니다. |
| `SMTP_USE_TLS` | 선택 | `true` | STARTTLS 사용 여부입니다. 미설정 시 `true`로 처리합니다. |
| `SMTP_USE_SSL` | 선택 | `false` | SMTP_SSL 사용 여부입니다. 미설정 시 `false`로 처리합니다. |
| `EMAIL_SUBJECT` | 선택 | `G마켓 베스트 크롤링 결과` | 이메일 제목을 고정하고 싶을 때 사용합니다. |

네이버 메일을 사용하는 경우 메일 서비스 설정에서 POP3/SMTP 사용이 허용되어 있어야 하며, 계정 보안 설정에 따라 별도 인증 또는 앱 비밀번호가 필요할 수 있습니다.

## 실행 방식

워크플로는 `.github/workflows/gmarket-best-daily.yml`에 정의되어 있습니다. `schedule` 이벤트는 UTC 기준으로 동작하므로, 한국시간 오전 9시는 UTC 0시에 해당합니다.[1]

```yaml
on:
  schedule:
    - cron: "0 0 * * *"
  workflow_dispatch:
```

`workflow_dispatch`도 함께 설정되어 있으므로 GitHub Actions 화면에서 **Run workflow** 버튼으로 수동 실행할 수 있습니다.[2]

## 크롤링 전략

크롤러는 기본적으로 `--mode auto`로 실행됩니다. 자동 모드는 먼저 `requests`로 `https://www.gmarket.co.kr/n/best` HTML을 받아 상품 DOM 또는 `__NEXT_DATA__`에 상품 데이터가 포함되어 있는지 확인합니다. 이 방식이 성공하면 브라우저를 실행하지 않으므로 GitHub Actions 서버 IP에서 브라우저 봇 탐지에 걸릴 가능성이 줄어듭니다.

| 단계 | 방식 | 성공 조건 | 비고 |
|---|---|---|---|
| 1 | `requests` HTML 수집 | `li.list-item` 또는 `__NEXT_DATA__` 상품 배열 존재 | 현재 G마켓이 봇 확인 HTML을 반환할 수 있습니다. |
| 2 | Next 초기 데이터 파싱 | `goodsCode`, `goodsName`, `discountPrice` 등 상품 배열 존재 | DOM 색상은 확인할 수 없으므로 가격 추출 메모에 대체 경로를 기록합니다. |
| 3 | Playwright fallback | 실제 DOM에서 `li.list-item` 렌더링 성공 | stealth init script, 시스템 Chrome/Chromium, Xvfb headed 모드를 사용합니다. |

## 로컬 테스트

로컬 PC에서 테스트하려면 Python 3.11 이상 환경에서 다음 명령을 실행합니다.

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
python gmarket_best_crawler.py --max-items 200 --mode auto

# G마켓 봇 확인 페이지가 표시되면 시스템 Chromium/Chrome과 Xvfb를 사용하세요.
xvfb-run -a python gmarket_best_crawler.py --max-items 200 --mode browser --headed --browser-executable-path /usr/bin/chromium
```

정상 실행되면 `output/` 디렉터리에 `gmarket_best_YYYYMMDD_HHMMSS.csv` 형식의 파일이 생성됩니다. 이메일 발송까지 테스트하려면 환경변수를 설정한 뒤 `send_email.py`를 실행합니다.

```bash
export SMTP_HOST="smtp.example.com"
export SMTP_PORT="587"
export SMTP_USERNAME="your_account@example.com"
export SMTP_PASSWORD="your_password_or_app_password"
export SMTP_FROM="your_account@example.com"
export SMTP_TO="dideum@naver.com"
export SMTP_USE_TLS="true"
export SMTP_USE_SSL="false"
python send_email.py
```

## CSV 컬럼

CSV는 UTF-8 BOM(`utf-8-sig`)으로 저장되어 Excel에서 한글이 깨질 가능성을 줄였습니다. 주요 컬럼은 아래와 같습니다.

| 컬럼 | 의미 |
|---|---|
| `rank` | 베스트 순위입니다. |
| `product_name` | 상품명입니다. |
| `final_price_krw` | 사용자 기준에 따라 추출한 최종가격입니다. |
| `sale_price_krw` | 판매가 텍스트 또는 초기 데이터에서 추출한 가격입니다. |
| `coupon_applied_price_krw` | 쿠폰 적용 가격으로 판별된 값입니다. |
| `original_price_krw` | 원가입니다. |
| `discount_rate_percent` | 할인율입니다. |
| `shipping_info` | 배송 정보입니다. |
| `goodscode` | G마켓 상품 코드입니다. |
| `product_url` | 상품 상세 URL입니다. |
| `image_url` | 상품 이미지 URL입니다. |
| `final_price_extraction_note` | 최종가격 추출에 사용된 기준입니다. |

## 봇 차단 관련 주의사항과 대안

G마켓은 GitHub Actions와 같은 공용 클라우드 서버 IP 또는 자동화 브라우저 접근을 봇으로 판단할 수 있습니다. 이번 구현은 `requests` 우선 시도, stealth init script, 시스템 Chrome/Chromium, Xvfb headed 실행을 포함하지만, 사이트 운영 정책상 **완벽한 우회는 보장할 수 없습니다**.

차단이 계속되면 다음 대안을 검토하세요.

| 대안 | 설명 | 장단점 |
|---|---|---|
| 개인 PC 또는 사내 서버에서 cron 실행 | 평소 접속 가능한 네트워크에서 동일 스크립트를 실행합니다. | GitHub Actions IP 차단 문제를 피할 가능성이 가장 높습니다. |
| 프록시 또는 고정 주거용 IP 사용 | Actions에서 허용 가능한 프록시를 환경변수로 연결합니다. | 비용과 운영 부담이 있으며, 서비스 약관을 확인해야 합니다. |
| 공식 제휴/API 확인 | G마켓 또는 판매자센터에서 제공 가능한 공식 데이터 경로를 확인합니다. | 안정성이 가장 높지만 별도 권한이 필요할 수 있습니다. |
| 수집 실패 시 artifact만 확인 | 이메일 전송 전 CSV 생성 여부와 로그를 확인합니다. | 장애 원인을 파악하는 보조 수단입니다. |

크롤링 결과가 비어 있거나 `G마켓이 현재 브라우저 실행 방식을 봇으로 판별했습니다`라는 오류가 나오면, GitHub Actions 실행 로그의 `fetch_method=...`, `rows=...`, `output=...` 값을 확인하세요. 이메일이 발송되지 않으면 SMTP 시크릿 이름, 포트, TLS/SSL 설정, 메일 서비스의 SMTP 사용 허용 여부를 점검해야 합니다.

## References

[1]: https://docs.github.com/en/actions/reference/events-that-trigger-workflows#schedule "GitHub Docs - Events that trigger workflows: schedule"
[2]: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onworkflow_dispatch "GitHub Docs - workflow_dispatch"
[3]: https://playwright.dev/python/docs/intro "Playwright for Python - Getting started"
