FROM python

COPY ./requirements.txt .

ARG PIP_ROOT_USER_ACTION=ignore
ARG PIP_NO_CACHE_DIR=1

RUN pip install --upgrade pip && \
    pip install -r requirements.txt

COPY . .

CMD ["./run.sh"]
