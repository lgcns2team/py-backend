
### 가상환경 생성
py -3.11 -m venv .venv

### 가상환경 들어가기
source .venv/Scripts/activate

### requirements.txt 설치
pip3 install -r requirements.txt

<<<<<<< HEAD
=======
### ttsSample/requirements.txt 설치
pip install -r ttsSample/requirements.txt

>>>>>>> 02bcd133b6a266602266715d5a9a183ee0780c0e
### migration 적용
python3 manage.py migrate

### 서버 실행
python3 manage.py runserver 8000

### 가상환경 끄기

끝나고 나면 deactivate를 해주면 됩니다.

deactivate