from django.shortcuts import render
from django.contrib.auth.models import User
from django.http import HttpResponse, HttpResponseNotFound, HttpResponsePermanentRedirect, JsonResponse
from django.contrib.auth.decorators import login_required
import configparser
from cbp.core import logs
from cbp.forms import AuthGroupsForm, BackupGroupsForm, DevicesForm
from re import findall
from configparser import ConfigParser
import sys
import os
from datetime import datetime


def check_superuser(request):
    try:
        if not User.objects.get(username=str(request.user)).is_superuser:
            return 0
        else:
            return 1
    except Exception:
        return 0


@login_required(login_url='accounts/login/')
def show_logs(request):
    if not check_superuser(request):
        return HttpResponsePermanentRedirect('/')
    return render(request, 'backup_control/logs.html')


@login_required(login_url='accounts/login/')
def get_logs(request):
    print(request.GET)
    if not check_superuser(request):
        return JsonResponse({
            'data': []
        })

    conf = ConfigParser()
    conf.read(f'{sys.path[0]}/cbp.conf')  # Файл конфигурации
    logs_dir = conf.get('Path', 'logs_dir').replace('~', sys.path[0])  # Папка сохранения логов

    if os.path.exists(os.path.join(logs_dir, f"{request.GET.get('type')}.log")):
        with open(os.path.join(logs_dir, f"{request.GET.get('type')}.log")) as file:
            log_file = file.readlines()
    else:
        return JsonResponse({
            'data': []
        })
    logs_data = [
        {
            'time': line[:19],
            'module': findall(r'\| (\S+)\s*[->]*', line[19:])[0],
            'content': findall(r'\| \S+\s*[->]*([\S\W]+)', line[19:])[0]
        }
        for line in log_file
    ]

    return JsonResponse({
        'data': logs_data
    })