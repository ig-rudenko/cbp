import shutil
import sys
import os
from datetime import datetime
from core import logs
import pexpect
from configparser import ConfigParser

timed = str(datetime.now())[0:10]   # текущая дата 'yyyy-mm-dd'

cfg = ConfigParser()
cfg.read(f'{sys.path[0]}/cbp.conf')
ftp_directory = cfg.get('FTP', 'directory')
if not os.path.exists(ftp_directory):
    os.makedirs(ftp_directory)
tftp_directory = cfg.get('TFTP', 'directory')
if not os.path.exists(tftp_directory):
    os.makedirs(tftp_directory)
ftp_user = cfg.get('FTP', 'username')
ftp_password = cfg.get('FTP', 'password')
backup_server_ip = cfg.get('Main', 'backup_server_ip')


def elog(info, ip, name):
    logs.error_log.error("%s-> %s: %s" % (ip.ljust(15, '-'), name, info))


def tftp_upload(telnet_session, device_name: str, device_ip: str, file_to_copy: str, backup_group: str):
    """
    Загрузка файла конфигурации по TFTP протоколу
    """
    telnet_session.sendline(f'tftp {backup_server_ip} upload {file_to_copy}')
    upload_status = telnet_session.expect(
        [
            r'bytes uploaded',  # 0 - успешно
            r'File not found',  # 1
            pexpect.TIMEOUT     # 2
        ],
        timeout=5
    )
    if upload_status == 2:
        telnet_session.sendcontrol('C')  # Прерываем
        elog('Таймаут при подключении к серверу', device_ip, device_name)

    telnet_session.expect(r'\(cfg-tffs\)#\s*$')
    # Удаляем файл
    telnet_session.sendline(f'remove {file_to_copy}')
    telnet_session.sendline(f'Yes')
    telnet_session.expect(r'\(cfg-tffs\)#\s*$')

    if upload_status == 1:
        elog(f'Файл {file_to_copy} не найден на устройстве', device_ip, device_name)

    elif upload_status == 0:
        uploaded_file = f'{tftp_directory}/{file_to_copy.split("/")[-1]}'
        if os.path.exists(uploaded_file):
            next_file = f'{ftp_directory}/{backup_group}/{device_name.strip()}/{timed}_{file_to_copy.split("/")[-1]}'
            shutil.move(uploaded_file, next_file)
            if not os.path.exists(next_file):
                elog(f"Файл конфигурации не был перенесен и находится в {uploaded_file}", device_ip, device_name)
            return True
        else:
            elog("Файл конфигурации не был загружен!", device_ip, device_name)
    return False


def get_configuration(telnet_session, privilege_mode_password: str) -> str:
    telnet_session.sendline('\n')
    if telnet_session.expect([r'\(cfg\)#\s*$', r'>\s*$']):
        telnet_session.sendline('enable')
        telnet_session.expect('pass')
        telnet_session.sendline(privilege_mode_password)
        telnet_session.expect(r'\(cfg\)#\s*$')
    telnet_session.sendline('show start-config')
    config = ''
    while True:
        m = telnet_session.expect(
                [
                    r'\(cfg\)#\s*$',
                    r'----- more ----- Press Q or Ctrl\+C to break -----',
                    pexpect.TIMEOUT
                ]
            )
        config += telnet_session.before.decode('utf-8')
        if m == 0:
            break
        elif m == 1:
            telnet_session.sendline(' ')
    return config


def backup(telnet_session, device_ip: str, device_name: str, backup_group: str, privilege_mode_password: str):
    """
    Загрузка файла конфигурации на удаленный сервер
    """
    telnet_session.sendline('\n')
    user_level = telnet_session.expect(
        [
            r'>$',
            r'\(cfg\)#\s*$',
            r'\(cfg-tffs\)#\s*$'
        ]
    )
    if user_level == 0:
        telnet_session.sendline('enable')
        telnet_session.expect('pass')
        telnet_session.sendline(privilege_mode_password)
        telnet_session.expect(r'\(cfg\)#\s*$')
        user_level = 1
    if user_level == 1:
        telnet_session.sendline('config tffs')
        telnet_session.expect(r'\(cfg-tffs\)#\s*$')

    # Проверка на доступность протокола ftp
    telnet_session.sendline('ftp')
    ftp_enable = telnet_session.expect(
        [
            r'Command not found',           # 0 - ftp недоступен
            r'Parameter not enough',        # 1 - ftp доступен
            r'Permission denied'            # 2 - доступ запрещен
            r'\(cfg-tffs\)#\s*$',           # 3 - точка выхода
        ]
    )

    if ftp_enable == 0:  # No ftp -> TFTP
        telnet_session.expect(r'\(cfg-tffs\)#\s*$')
        telnet_session.sendline(f'copy startcfg.txt {device_name}_startcfg.txt')  # Копирование файла на коммутаторе
        file_to_copy = f'{timed}_startrun.txt'
        copy_status = telnet_session.expect(
            [
                'bytes copied',         # 0 - успешно
                'File exists'           # 1
                'File does not exist',  # 2
            ]
        )
        telnet_session.expect(r'\(cfg-tffs\)#\s*$')

        if copy_status == 1:    # Файл уже существует
            telnet_session.sendline(f'remove {device_name}_startcfg.txt')
            telnet_session.sendline(f'Yes')
            telnet_session.expect(r'\(cfg-tffs\)#\s*$')
            telnet_session.sendline(f'copy startcfg.txt {device_name}_startcfg.txt')  # Копирование файла на коммутаторе
            telnet_session.expect(r'\(cfg-tffs\)#\s*$')
        elif copy_status == 2:  # Файл не найден
            telnet_session.sendline('cd cfg')   # Меняем директорию
            telnet_session.expect(r'\(cfg-tffs\)#\s*$')
            telnet_session.sendline(f'copy startrun.dat {device_name}_startrun.dat')
            file_to_copy = f'/cfg/{device_name}_startrun.dat'

        return tftp_upload(telnet_session, device_name, device_ip, file_to_copy, backup_group)

    elif ftp_enable == 1:  # FTP
        telnet_session.expect(r'\(cfg-tffs\)#\s*$')
        # Если нет папки - создаем
        if not os.path.exists(f'{ftp_directory}/{backup_group}/{device_name}'):
            os.makedirs(f'{ftp_directory}/{backup_group}/{device_name}')

        # Отправляем файл конфигурации
        telnet_session.sendline(f'ftp {backup_server_ip} {backup_group}/{device_name}/{timed}_startrun.dat upload '
                                f'/cfg/startrun.dat username {ftp_user} password {ftp_password}')

        upload_status = telnet_session.expect(
            [
                r'bytes uploaded',                       # 0 - успешно
                r'No such file or directory',            # 1
                r'No such file or directory \(0',        # 2
                r'Command not found',                    # 3
                r'\(cfg-tffs\)#\s*$',                    # 4 - точка выхода
                pexpect.TIMEOUT                          # 5
            ]
        )

        if upload_status == 1:
            elog(f'Директория отсутствует: {ftp_directory}/{backup_group}/{device_name}', device_ip, device_name)
        elif upload_status == 2:
            elog(f'Файл /cfg/startrun.dat Отсутствует на данном устройстве', device_ip, device_name)
        elif upload_status == 3:
            elog(f'Команда не найдена', device_ip, device_name)
        elif upload_status == 5:
            telnet_session.sendcontrol('C')  # Прерываем
            elog('Таймаут при подключении к серверу ', device_ip, device_name)
        else:
            elog(f'{telnet_session.before.decode("utf-8")}', device_ip, device_name)

        return True if not upload_status else False

    elif ftp_enable == 2:
        elog(f'Запрещен доступ к {ftp_directory}/{backup_group}/{device_name}', device_ip, device_name)
    return False
