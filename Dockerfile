FROM python:3.9.6
WORKDIR /app
COPY . /app
RUN pip install -Ur requirements.txt
ENTRYPOINT ["python3", "-m",  "dozer"]
