"""Получение прямых зависимостей из индекса Ubuntu Packages."""

import bz2
import gzip
from http.client import HTTPException
import lzma
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


TIMEOUT = 15
DEFAULT_INDEX = "dists/noble/main/binary-amd64/Packages.xz"
INDEX_NAMES = ("Packages", "Packages.xz", "Packages.gz", "Packages.bz2")
GZIP_MAGIC = b"\x1f\x8b"
XZ_MAGIC = b"\xfd7zXZ\x00"
BZ2_MAGIC = b"BZh"
FIELD_PATTERN = re.compile(r"[!-9;-~]+")


def get_index_url(repository):
    """Принять URL индекса или построить путь от корня репозитория."""
    address = urlsplit(repository)
    if address.path.rsplit("/", 1)[-1] in INDEX_NAMES:
        return repository
    if address.query or address.fragment:
        raise ValueError(
            "Для URL корня репозитория не задавайте query или fragment; "
            "можно указать прямой URL файла Packages."
        )
    path = address.path.rstrip("/") + "/" + DEFAULT_INDEX
    return urlunsplit((address.scheme, address.netloc, path, "", ""))


def download_index(url):
    """Загрузить байты индекса по HTTP без менеджеров пакетов."""
    request = Request(url, headers={
        "User-Agent": "apt-dependency-visualizer/0.2"
    })
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            return response.read()
    except HTTPError as error:
        raise ValueError(
            f"Сервер вернул HTTP {error.code} при загрузке индекса."
        ) from error
    except (URLError, OSError, HTTPException) as error:
        raise ValueError(
            "Не удалось загрузить индекс репозитория: " + str(error)
        ) from error


def decode_index(data):
    """Распаковать индекс по сигнатуре и прочитать текст UTF-8."""
    try:
        if data.startswith(GZIP_MAGIC):
            data = gzip.decompress(data)
        elif data.startswith(XZ_MAGIC):
            data = lzma.decompress(data)
        elif data.startswith(BZ2_MAGIC):
            data = bz2.decompress(data)
    except (OSError, EOFError, ValueError, lzma.LZMAError) as error:
        raise ValueError("Сжатый индекс повреждён или неполон.") from error
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Индекс репозитория должен быть в UTF-8.") from error


def parse_field(line, number):
    """Разобрать одну строку поля и проверить допустимость имени."""
    name, separator, value = line.partition(":")
    if not separator or not FIELD_PATTERN.fullmatch(name):
        raise ValueError(f"Некорректное поле индекса в строке {number}.")
    if name.startswith(("#", "-")):
        raise ValueError(f"Некорректное имя поля в строке {number}.")
    return name.lower(), value.strip()


def iter_package_records(text):
    """Прочитать абзацы Packages с учётом продолжений строк полей."""
    record = {}
    previous = None
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            if record:
                yield record
            record, previous = {}, None
            continue
        if line.startswith((" ", "\t")):
            if previous is None:
                raise ValueError(
                    f"Продолжение без начального поля в строке {number}."
                )
            record[previous] += "\n" + line[1:]
            continue
        name, value = parse_field(line, number)
        if name in record:
            raise ValueError(f"Поле {name} повторяется в строке {number}.")
        record[name] = value
        previous = name
    if record:
        yield record


def find_package(text, package):
    """Найти единственную запись выбранного пакета в конкретном индексе."""
    found = None
    for record in iter_package_records(text):
        if record.get("package") != package:
            continue
        if found is not None:
            raise ValueError(
                f"Несколько записей пакета {package}: используйте индекс "
                "с одной версией пакета для выбранной архитектуры."
            )
        found = record
    if found is None:
        raise ValueError(f"Пакет {package} не найден в указанном индексе.")
    return found


def extract_dependencies(record):
    """Извлечь группы обязательных зависимостей, сохраняя их условия."""
    result = []
    for name, label in (("pre-depends", "Pre-Depends"), ("depends", "Depends")):
        value = record.get(name)
        if value is None:
            continue
        # Запятая разделяет группы, а вертикальная черта внутри — альтернативы.
        for group in value.split(","):
            expression = " ".join(group.split())
            if not expression:
                raise ValueError(f"Пустая группа зависимостей в поле {label}.")
            result.append((label, expression))
    return result


def get_direct_dependencies(repository, package):
    """Загрузить индекс, найти пакет и вернуть его прямые зависимости."""
    url = get_index_url(repository)
    text = decode_index(download_index(url))
    record = find_package(text, package)
    return extract_dependencies(record)
