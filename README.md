# G마켓 베스트 일일 크롤러

이 저장소는 **G마켓 베스트 페이지**에서 1위부터 200위까지의 상품 정보를 매일 수집하고, 생성된 CSV 파일을 이메일로 전송하도록 구성되어 있습니다. 크롤링은 Playwright 기반 브라우저 자동화로 수행되며, GitHub Actions의 예약 실행은 한국시간 기준 매일 오전 9시에 맞춰 UTC 0시 cron으로 설정되어 있습니다.[1][2]

검증 과정에서 G마켓이 Playwright 번들 Chromium의 순수 headless 실행을 봇 확인 페이지로 전환하는 경우가 확인되었습니다. 따라서 workflow는 GitHub Actions 러너에 설치된 시스템 Chrome 또는 Chromium을 우선 사용하고, Xvfb 가상 디스플레이에서 `--headed` 옵션으로 실행하도록 구성했습니다. 이 방식은 서버 환경에서 화면 없이 동작하지만, 브라우저 자체는 headed 모드로 실행됩니다.

> 최종가격 추출 기준은 `.box__price-seller span.text.text__value`입니다. 동일 선택자 안에서 빨간색 `#DA120D` 가격이 있으면 그 값을 최우선으로 사용하고, 빨간색 가격이 없으면 검정색 `#424242` 가격을 사용합니다.

## 구성 파일

| 파일 | 역할 |
|---|---|
| `gmarket_best_crawler.py` | G마켓 베스트 페이지를 렌더링하고 1~200위 상품을 CSV로 저장합니다. |
| `send_email.py` | 생성된 CSV 파일을 SMTP 이메일 첨부로 발송합니다. |
| `.github/workflows/gmarket-best-daily.yml` | 매일 KST 09:00, 즉 UTC 00:00에 크롤링과 이메일 발송을 실행합니다. |
| `requirements.txt` | Python 실행에 필요한 패키지를 정의합니다. |
| `.gitignore` | 로컬 실행 산출물과 민감 정보 파일이 커밋되지 않도록 제외합니다. |

## GitHub 저장소 생성 및 업로드

GitHub 사용자명 `jun0289jun` 계정에서 새 저장소를 생성한 뒤, 이 폴더의 파일을 그대로 업로드하면 됩니다. 예를 들어 저장소명을 `gmarket-best-crawler`로 만들었다면 최종 주소는 다음과 같은 형태가 됩니다.

```text
https://github.com/jun0289jun/gmarket-best-crawler
```

로컬에서 Git 명령으로 업로드하려면 아래처럼 진행할 수 있습니다.

```bash
git init
git add .
git commit -m "Add daily Gmarket best crawler"
git branch -M main
git remote add origin https://github.com/jun0289jun/gmarket-best-crawler.git
git push -u origin main
```

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

네이버 메일을 사용하는 경우 메일 서비스 설정에서 POP3/SMTP 사용이 허용되어 있어야 하며, 계정 보안 설정에 따라 별도 인증 또는 앱 비밀번호가 필요할 수 있습니다. SMTP 설정값은 사용하는 메일 서비스의 공식 안내를 기준으로 확인하세요.

## 실행 방식

워크플로는 `.github/workflows/gmarket-best-daily.yml`에 정의되어 있습니다. `schedule` 이벤트는 UTC 기준으로 동작하므로, 한국시간 오전 9시는 UTC 0시에 해당합니다.[1]

```yaml
on:
  schedule:
    - cron: "0 0 * * *"
  workflow_dispatch:
```

`workflow_dispatch`도 함께 설정되어 있으므로 GitHub Actions 화면에서 **Run workflow** 버튼으로 수동 실행할 수 있습니다.[3]

## 로컬 테스트

로컬 PC에서 테스트하려면 Python 3.11 이상 환경에서 다음 명령을 실행합니다.

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
python gmarket_best_crawler.py --max-items 200

# G마켓 봇 확인 페이지가 표시되면 시스템 Chromium/Chrome과 Xvfb를 사용하세요.
xvfb-run -a python gmarket_best_crawler.py --max-items 200 --headed --browser-executable-path /usr/bin/chromium
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
| `sale_price_krw` | 판매가 텍스트에서 추출한 가격입니다. |
| `coupon_applied_price_krw` | 쿠폰 적용 가격으로 판별된 값입니다. |
| `original_price_krw` | 원가입니다. |
| `discount_rate_percent` | 할인율입니다. |
| `shipping_info` | 배송 정보입니다. |
| `goodscode` | G마켓 상품 코드입니다. |
| `product_url` | 상품 상세 URL입니다. |
| `image_url` | 상품 이미지 URL입니다. |
| `final_price_extraction_note` | 최종가격 추출에 사용된 기준입니다. |

## 문제 해결

크롤링 결과가 비어 있거나 `G마켓이 현재 브라우저 실행 방식을 봇으로 판별했습니다`라는 오류가 나오면, 순수 headless 실행이 차단된 상태입니다. 이 저장소의 workflow처럼 시스템 Chrome 또는 Chromium을 `BROWSER_EXECUTABLE_PATH`로 지정하고 `xvfb-run`과 `--headed` 옵션을 함께 사용하세요. GitHub Actions 실행 로그에서 `rows=...`와 `output=...` 값을 확인하면 수집 건수와 CSV 생성 경로를 알 수 있습니다. 이메일이 발송되지 않으면 SMTP 시크릿 이름, 포트, TLS/SSL 설정, 메일 서비스의 SMTP 사용 허용 여부를 점검해야 합니다.

## References

[1]: https://docs.github.com/en/actions/reference/events-that-trigger-workflows#schedule "GitHub Docs - Events that trigger workflows: schedule"
[2]: https://playwright.dev/python/docs/intro "Playwright for Python - Getting started"
[3]: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onworkflow_dispatch "GitHub Docs - workflow_dispatch"
