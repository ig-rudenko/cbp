#!/bin/bash

python manage.py makemigrations;
python manage.py migrate;
python manage.py makemigrations cbp;
python manage.py migrate cbp;

if [ "$DJANGO_SUPERUSER_NAME" ] && [ "$DJANGO_SUPERUSER_PASSWORD" ]
  then
    python manage.py createsuperuser --username "$DJANGO_SUPERUSER_NAME" --noinput --email "$DJANGO_SUPERUSER_EMAIL" || true ; echo $?;
  else
    python manage.py createsuperuser --username root --noinput --email root@example.com || true ; echo $?;
fi

if [ "$DJANGO_PORT" ]
  then
    python manage.py runserver 0.0.0.0:$DJANGO_PORT;
  else
    python manage.py runserver 0.0.0.0:8000;
fi
