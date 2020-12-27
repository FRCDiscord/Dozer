FROM debian
WORKDIR /app
COPY . /app
RUN apt update
RUN apt install -y build-essential libssl-dev zlib1g-dev libbz2-dev \
    libreadline-dev libsqlite3-dev wget curl llvm libncurses5-dev libncursesw5-dev \
    xz-utils tk-dev libffi-dev liblzma-dev python-openssl git
RUN curl https://pyenv.run | bash
ENV PATH="/root/.pyenv/bin:$PATH"
RUN eval "$(pyenv init -)"
RUN eval "$(pyenv virtualenv-init -)"
RUN pyenv install 3.8.2
RUN pyenv global 3.8.2
RUN /root/.pyenv/shims/python3 -m pip install -Ur requirements.txt
ENTRYPOINT ["/root/.pyenv/shims/python3", "-m",  "dozer"]
