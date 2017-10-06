@echo off
echo Pulling code from github
git pull
echo Updating Dependencies
python -m pip install -Ur requirements.txt
echo Starting Dozer
python -m dozer
pause