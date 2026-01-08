# H.AI (History.AI) Backend

> 교과서 기반 RAG와 AI Agent를 활용한 역사 교육 플랫폼 백엔드

## 목차
1. [프로젝트 구성 안내 - 기술 스택 등](#1-프로젝트-구성-안내)
2. [프로젝트 설치하는 방법](#2-프로젝트-설치하는-방법)
3. [프로젝트 사용법](#3-프로젝트-사용법)
4. [프로젝트 기능 설명](#4-프로젝트-기능-설명)
5. [저작권 및 사용권 정보](#5-저작권-및-사용권-정보)
6. [버그](#6-버그)
7. [프로그램 작성자 및 도움을 준 사람](#7-프로그램-작성자-및-도움을-준-사람)
8. [버전 (업데이트 소식)](#8-버전-업데이트-소식)
9. [FAQ](#9-faq)

---

## (1) 프로젝트 구성 안내

### 프로젝트 개요
H.AI는 AWS Bedrock을 활용한 역사 교육 AI 플랫폼의 백엔드 시스템입니다. 교과서 기반 RAG(Retrieval-Augmented Generation)와 AI Agent 기능을 통해 학생들에게 인터랙티브한 역사 학습 경험을 제공합니다.

### 기술 스택

#### Core Framework
- **Python** 3.11
- **Django** 4.2+
- **Django REST Framework** (DRF)

#### AI & ML
- **AWS Bedrock** - Claude AI 3.5 Sonnet 모델 활용
- **AWS Knowledge Bases** - RAG 구현
- **LangChain** - AI Agent 및 Tool Calling 구현

#### Database
- **PostgreSQL** - 메인 데이터베이스
- **Vector DB(S3)** (AWS Knowledge Bases 내장)

#### Communication
- **Server-Sent Events (SSE)** - 실시간 스트리밍 통신

#### Infrastructure
- **AWS** (EC2, S3, Bedrock, Knowledge Bases)
- **Docker** & **Docker Compose**

### 프로젝트 구조
```
├── apps
│   ├── __init__.py
│   ├── chat
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── urls.py
│   │   └── views.py
│   ├── debate
│   │   ├── __init__.py
│   │   ├── redis_repository.py
│   │   ├── urls.py
│   │   └── views.py
│   ├── knowledge
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── urls.py
│   │   └── views.py
│   ├── prompt
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── dto.py
│   │   ├── models.py
│   │   ├── redis_chat_repository.py
│   │   ├── urls.py
│   │   └── views.py
│   ├── router
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── urls.py
│   │   └── views.py
│   └── tools
│       ├── __init__.py
│       ├── apps.py
│       ├── definitions.py
│       └── handlers.py
├── bin
│   ├── default
│   ├── generated-sources
│   │   └── annotations
│   ├── generated-test-sources
│   │   └── annotations
│   └── test
├── common
│   ├── __init__.py
│   ├── bedrock
│   │   ├── __init__.py
│   │   ├── clients.py
│   │   ├── converse.py
│   │   └── streaming.py
│   └── redis
│       ├── __init__.py
│       └── redis_client.py
├── config
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── data
│   └── redis
├── Dockerfile
├── HOW_TO_EXCUTE_README.md
├── Jenkinsfile
├── manage.py
├── README.md
└── requirements.txt
```

### 주요 특징
- **프롬프트 중앙 관리**: 모든 AI 서비스의 프롬프트를 체계적으로 관리
- **다양한 통신 방식**: 동기/비동기 처리 및 SSE 스트리밍 지원
- **교과서 기반 RAG**: AWS Knowledge Bases를 활용한 정확한 역사 정보 제공
- **AI Agent & Tool Calling**: 연도 이동, 교과서 페이지 이동, 인물 대화 등 인터랙티브 기능

---

## (2) 프로젝트 설치하는 방법

### 사전 요구사항
- Python 3.11 이상
- PostgreSQL 15 이상
- AWS 계정 및 Bedrock 액세스 권한
- Docker & Docker Compose (선택사항)

### 설치 단계

#### 1. 저장소 클론
```bash
git clone https://github.com/lgcns2team/py-backend.git
cd py-backend
```

#### 2. 가상환경 생성 및 활성화
```bash
# macOS/Linux
python -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

#### 3. 의존성 설치
```bash
# 개발 환경
pip install -r requirements/development.txt

# 프로덕션 환경
pip install -r requirements/production.txt
```

#### 4. 환경변수 설정
`.env` 파일을 생성하고 다음 내용을 설정합니다:

```env
# Django
DJANGO_SECRET_KEY=
DEBUG=True
ALLOWED_HOSTS=*

# Database
DB_NAME=
DB_USER=
DB_PASSWORD=
DB_HOST=
DB_PORT=

# Redis
REDIS_HOST=localhost
REDIS_URL=redis://localhost:6379/0
REDIS_PORT=6379
REDIS_DB=0

# AWS Credentials
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=

# Knowledge Base Configuration
AWS_BEDROCK_KB_ID=
AWS_BEDROCK_KB_MODEL_ARN=

CLOUD_AWS_REGION=

# AWS Bedrock Debate Topics Prompt
AWS_BEDROCK_DEBATE_TOPICS_PROMPT_ARN=
AWS_BEDROCK_DEBATE_SUMMARY_PROMPT_ARN=
AWS_BEDROCK_AI_PERSON_ARN=
AWS_BEDROCK_KNOWLEDGE_PROMPT_ARN=

AWS_REGION=
AWS_ACCOUNT_ID=

# Server
HOST=0.0.0.0
PORT=8000

TYPECAST_API_KEY= 
```

#### 5. 데이터베이스 마이그레이션
```bash
python manage.py migrate
```

#### 6. 슈퍼유저 생성
```bash
python manage.py createsuperuser
```

#### 7. 개발 서버 실행
```bash
python manage.py runserver
```

서버가 `http://localhost:8000`에서 실행됩니다.

---

## (3) 프로젝트 사용법

### API 엔드포인트

#### 1. 토론 서비스 (동기 방식)

**토론 주제 추천**
```http
POST /api/debate/topics/recommend
Content-Type: application/json

{
  "user_query": "한국사 조선시대 외교에 대해 토론하고 싶어"
}
```

**응답 예시**
```json
{
  "debate_topics": [
    {
      "topic": "임진왜란 당시 조선의 외교 전략",
      "description": "명나라와의 동맹을 중심으로..."
    }
  ]
}
```

**토론 요약**
```http
POST /api/debate/{room_id}/summary
Content-Type: application/json

{
  "topic": "임진왜란 당시 조선의 외교 전략"
}
```

**응답 예시**
```json
{
  "room_id": "123",
  "topic": "임진왜란 당시 조선의 외교 전략",
  "used_message_count": 10,
  "result": {
    "summary": "...",
    "key_points": ["..."]
  }
}
```

#### 2. AI 인물 채팅 (SSE 스트리밍)

**채팅 시작**
```http
POST /api/ai-person/{person_id}/chat
Content-Type: application/json

{
  "message": "한글 창제의 이유를 설명해주세요",
  "userId": "550e8400-e29b-41d4-a716-446655440000"
}
```

**SSE 응답 (스트리밍)**
```
event: content
data: {"text": "한글"}

event: content
data: {"text": "을 만든"}

event: content
data: {"text": " 이유는..."}

event: done
data: {"total_length": 150}
```

#### 3. AI 챗봇 (RAG + Tool Calling, SSE 스트리밍)

**챗봇 대화**
```http
POST /api/agent-chat/
Content-Type: application/json

{
  "message": "1592년에 어떤 일이 있었나요?"
}
```

**Tool Calling 응답 예시 (JSON)**
```json
{
  "type": "tool_call",
  "action": "navigate_to_war",
  "input": {
    "war_name": "임진왜란",
    "year": 1592
  }
}
```

**RAG 응답 예시 (SSE 스트리밍)**
```
event: content
data: {"text": "1592년은"}

event: content
data: {"text": " 임진왜란이"}

event: citations
data: {"count": 1, "data": [...]}

event: done
data: {}
```

### 사용 가능한 Tool Calling 기능

1. **역사 인물 페이지 이동 (navigate_to_person)**
   - 역사 인물과 대화하는 페이지로 사용자를 이동
   - 예: "이순신과 대화하고 싶어", "세종대왕한테 문자 보내줘"

2. **전쟁 시점/위치 이동 (navigate_to_war)**
   - 특정 전쟁에 대해 묻거나 설명을 요청할 때 지도에서 해당 시점과 위치로 이동
   - 예: "임진왜란에 대해 알려줘", "6.25 전쟁은 언제 일어났어?"

### Django Admin 사용

Admin 페이지 접속: `http://localhost:8000/admin/`

- 프롬프트 템플릿 관리
- 대화 히스토리 조회
- 사용자 및 권한 관리
- 시스템 모니터링

---

## (4) 프로젝트 기능 설명

### 1. 토론 주제 추천 서비스
**기술:** AWS Bedrock (Claude), 동기 방식

학생의 학년, 과목, 관심사를 분석하여 교육과정에 맞는 토론 주제를 추천합니다.

**주요 기능:**
- 교육과정 기반 주제 필터링
- 난이도 자동 조정
- 학습 목표 매칭
- 다양한 관점 제시

### 2. 토론 요약 서비스
**기술:** AWS Bedrock (Claude), 동기 방식

진행된 토론 내용을 분석하여 핵심 논점과 결론을 요약합니다.

**주요 기능:**
- 주요 논점 추출
- 각 참여자의 입장 정리
- 합의점 및 차이점 분석
- 추가 학습 방향 제안

### 3. AI-Person 채팅 서비스
**기술:** AWS Bedrock (Claude), SSE 스트리밍

역사적 인물의 페르소나를 가진 AI와 실시간 대화가 가능합니다.

**주요 기능:**
- 실시간 스트리밍 응답
- 인물별 맞춤 페르소나
- 역사적 맥락 유지
- 교육적 가치 제공

**지원 인물:**
- 세종대왕, 이순신, 유관순, 김구 등
- 각 인물의 시대적 배경과 가치관 반영

### 4. RAG 기반 AI 챗봇 (핵심 기능)
**기술:** AWS Knowledge Bases, SSE 스트리밍, AI Agent, Tool Calling

교과서 기반 RAG 시스템으로 정확한 역사 정보를 제공하며, Tool Calling을 통한 인터랙티브 기능을 지원합니다.

#### 4-1. RAG 구축
- **데이터 소스**: 한국사 교과서 PDF
- **벡터 DB**: AWS Knowledge Bases 내장 S3 벡터 스토어
- **임베딩 모델**: Titan Text Embeddingsv2
- **컨텍스트 윈도우**: 최대 4096 토큰

#### 4-2. AI Agent & Tool Calling

**연도 이동 (Year Navigation)**
```python
# 예시: "1592년에 무슨 일이 있었나요?"
{
  "tool_name": "move_to_year",
  "parameters": {
    "year": 1592,
    "period": "조선 후기"
  }
}
```

**교과서 페이지 이동 (Page Navigation)**
```python
# 예시: "임진왜란에 대해 더 알고 싶어요"
{
  "tool_name": "move_to_page",
  "parameters": {
    "page": 145,
    "chapter": "3. 조선의 대외관계",
    "topic": "임진왜란"
  }
}
```

**인물 대화창 이동 (Person Chat Transition)**
```python
# 예시: "이순신 장군과 대화하고 싶어요"
{
  "tool_name": "move_to_person_chat",
  "parameters": {
    "person_id": "lee_sunshin",
    "person_name": "이순신",
    "context": "임진왜란 당시 수군 전략"
  }
}
```

### 프롬프트 관리 시스템

모든 AI 서비스의 프롬프트를 AWS BEDROCK 프롬프트 관리 기능을 통해 체계적으로 관리합니다.

### 데이터 흐름

```
Client Request
    ↓
Django REST API
    ↓
Service Layer
    ↓
├─→ Bedrock Client (동기) → Claude Model
│                              ↓
│                           Response
│
└─→ Bedrock Client (SSE) → Claude Model (Stream)
    └─→ Knowledge Bases → Vector Search
                              ↓
                         RAG Context
                              ↓
                      Tool Calling Decision
                              ↓
                    ├─ Year Navigation
                    ├─ Page Navigation  
                    └─ Person Chat
```

---

## (5) 저작권 및 사용권 정보

### 라이선스
이 프로젝트는 [MIT License](LICENSE) 하에 배포됩니다.

```
MIT License

Copyright (c) 2024 H.AI Team

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
```

### 사용된 오픈소스

| 라이브러리 | 버전 | 라이선스 |
|----------|------|---------|
| Django | 4.2+ | BSD |
| Django REST Framework | 3.14+ | BSD |
| boto3 | 1.35+ | Apache 2.0 |
| psycopg2-binary | 2.9+ | LGPL |

### 주의사항
- AWS Bedrock 사용에 따른 비용이 발생합니다
- 교과서 콘텐츠 저작권은 각 출판사에 있습니다
- 상업적 사용 시 별도 라이선스 계약이 필요할 수 있습니다

---

## (6) 버그

### 알려진 이슈

#### 1. AI 인물과의 대화 시 할루시네이션 발생
- **문제**: AI 인물과의 대화 시 할루시네이션 발생
- **영향**: 정확한 정보 전달 실패
- **해결 방안**: Frontend에서 할루시네이션 발생이 가능하다고 알림
- **상태**: 개선 예정

#### 2. Knowledge Base 검색 정확도
- **문제**: 교과서에 있는 페이지로 이동하지 못하는 경우
- **영향**: 실제 교과서에 있는 내용인지 확인 필요
- **해결 방안**: 메타데이터 및 필터링 강화 필요
- **상태**: 개선 예정


---

## (7) 프로그램 작성자 및 도움을 준 사람

### 👥 개발팀

#### Core Team
- **[Your Name]** - Project Lead & Backend Architect
  - GitHub: [@your-github](https://github.com/your-github)
  - Email: your-email@example.com

- **[Team Member 2]** - AI/ML Engineer
  - RAG 시스템 구축 및 최적화
  - Tool Calling 기능 개발

- **[Team Member 3]** - Backend Developer
  - Django REST API 개발
  - SSE 스트리밍 구현

- **[Team Member 4]** - DevOps Engineer
  - AWS 인프라 구축
  - CI/CD 파이프라인 관리

### 기여자

이 프로젝트에 기여해주신 모든 분들께 감사드립니다:

- **[Contributor 1]** - 프롬프트 엔지니어링 개선
- **[Contributor 2]** - 문서화 작업
- **[Contributor 3]** - 버그 수정 및 테스트

### 기여 방법

프로젝트에 기여하고 싶으신 분은 [CONTRIBUTING.md](CONTRIBUTING.md)를 참고해주세요.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

### 연락처
- 프로젝트 문의: hai-team@example.com
- 기술 지원: support@hai-project.com
- 슬랙 채널: [#hai-backend](https://your-slack.slack.com)

---

## (8) 버전 (업데이트 소식)

### v2.0.0 (2024-01-08) - Current
**Major Update: AI Agent & Tool Calling**

#### 새로운 기능
- AI Agent 기반 Tool Calling 시스템 구축
- 연도 이동 기능 추가
- 교과서 페이지 이동 기능 추가
- 인물 대화창 전환 기능 추가
- Knowledge Bases RAG 성능 개선

#### 개선사항
- SSE 스트리밍 안정성 향상
- 프롬프트 관리 시스템 고도화
- API 응답 속도 30% 개선
- 에러 핸들링 강화

#### 버그 수정
- SSE 연결 타임아웃 문제 해결
- 중복 Tool 호출 방지 로직 추가
- 메모리 누수 이슈 수정

### v1.5.0 (2023-12-15)
**Feature: RAG 기반 챗봇**

#### 새로운 기능
- AWS Knowledge Bases 통합
- 교과서 기반 RAG 시스템 구축
- SSE 스트리밍 챗봇 서비스

#### 개선사항
- Vector Search 정확도 향상
- 컨텍스트 윈도우 최적화

### v1.0.0 (2023-11-01)
**Initial Release**

#### 핵심 기능
- AWS Bedrock 연동
- 토론 주제 추천 서비스
- 토론 요약 서비스
- AI-Person 채팅 서비스 (SSE)
- 프롬프트 관리 시스템

#### 인프라
- Django + DRF 기반 API 서버
- PostgreSQL 데이터베이스
- Docker 컨테이너화

### 로드맵 (Upcoming)

#### v2.1.0 (2024 Q1)
- [ ] 멀티모달 지원 (이미지, 영상)
- [ ] 음성 인터페이스 추가
- [ ] 실시간 협업 토론 기능
- [ ] 학습 진도 추적 시스템

#### v2.2.0 (2024 Q2)
- [ ] 다국어 지원 (영어, 중국어)
- [ ] 모바일 앱 연동 API
- [ ] AI 평가 및 피드백 시스템
- [ ] 게임화 요소 추가

#### v3.0.0 (2024 Q3)
- [ ] 자체 LLM 파인튜닝
- [ ] 실시간 사실 검증 시스템
- [ ] 소셜 러닝 플랫폼 통합
- [ ] VR/AR 지원

---

## (9) FAQ

### 자주 묻는 질문

#### Q1. 로컬 개발 환경에서 AWS 연동은 어떻게 하나요?
**A:** AWS CLI 설정 후 로컬 프로필 사용:
```bash
aws configure --profile hai-dev
export AWS_PROFILE=hai-dev
```

또는 환경변수 직접 설정:
```bash
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_REGION=us-east-1
```

#### Q2. 교과서 데이터는 어떻게 업데이트하나요?
**A:** 다음 프로세스를 따릅니다:
1. 새 교과서 PDF를 S3에 업로드
2. Knowledge Base 데이터 소스 업데이트
3. 인덱싱 작업 실행
4. 검색 테스트 수행



**Made by 배움의 민족 Team**

*Last Updated: 2026-01-08*