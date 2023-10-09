python -m venv venv
call %~dp0\venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pause