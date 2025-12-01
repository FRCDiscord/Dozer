FROM python:3.10.19
WORKDIR /app
COPY . /app
RUN pip install -Ur requirements.txt
ENTRYPOINT ["python3", "-m",  "dozer"]
