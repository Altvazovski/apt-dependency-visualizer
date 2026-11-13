"""Первый этап визуализатора зависимостей Ubuntu: настройки CLI."""

import argparse
from pathlib import Path
import re
from urllib.parse import urlsplit


SUCCESS = 0


def validate_package(value, test_mode):
    """Проверить имя Ubuntu-пакета или тестовой вершины."""
    # В тестовом репозитории используются заглавные латинские буквы.
    pattern = r"[A-Z]+" if test_mode else r"[a-z0-9][a-z0-9+.-]+"
    if re.fullmatch(pattern, value):
        return
    if test_mode:
        raise ValueError("--package: нужны заглавные буквы A-Z.")
    raise ValueError(
        "--package: нужны минимум два символа: строчные буквы a-z, "
        "цифры, '+', '-' или '.'; первый символ — буква или цифра."
    )


def validate_url(value):
    """Проверить схему, наличие узла, порт и символы URL."""
    if any(char.isspace() or not char.isprintable() for char in value):
        raise ValueError("--repository: URL содержит недопустимые символы.")
    try:
        address = urlsplit(value)
        # Свойство port дополнительно проверяет формат и диапазон порта.
        _ = address.port
    except ValueError as error:
        raise ValueError("--repository: некорректный URL или порт.") from error
    if address.scheme not in ("http", "https") or not address.hostname:
        raise ValueError("--repository: нужен полный URL HTTP или HTTPS.")


def validate_file(value):
    """Проверить существование и доступность тестового файла."""
    path = Path(value)
    try:
        if not path.is_file():
            raise ValueError("--repository: тестовый файл не найден.")
        # На первом этапе проверяем доступ, не разбирая содержимое графа.
        with path.open("rb"):
            pass
    except OSError as error:
        raise ValueError("--repository: не удалось открыть файл.") from error


def validate_filter(value):
    """Разрешить пустой фильтр или подстроку без управляющих символов."""
    if value and (not value.strip() or not value.isprintable()):
        raise ValueError(
            "--filter: нужна подстрока без управляющих символов; "
            "значение только из пробелов недопустимо."
        )


def validate_args(args):
    """Проверить настройки с учётом выбранного источника данных."""
    validate_package(args.package, args.test_mode)
    if args.test_mode:
        validate_file(args.repository)
    else:
        validate_url(args.repository)
    validate_filter(args.filter)


def parse_args(argv=None):
    """Прочитать четыре параметра варианта 14 и обработать ошибки."""
    parser = argparse.ArgumentParser(
        description="Визуализатор зависимостей Ubuntu/apt: этап 1.",
        allow_abbrev=False
    )
    parser.add_argument(
        "--package", required=True, help="Имя анализируемого пакета"
    )
    parser.add_argument(
        "--repository", required=True,
        help="URL репозитория или путь к тестовому файлу"
    )
    # Переключатель включается самим присутствием в командной строке.
    parser.add_argument(
        "--test-mode", action="store_true",
        help="Использовать локальный тестовый репозиторий"
    )
    parser.add_argument(
        "--filter", default="", help="Подстрока для исключения пакетов"
    )
    args = parser.parse_args(argv)
    try:
        validate_args(args)
    except ValueError as error:
        parser.error(str(error))
    return args


def print_settings(args):
    """Вывести все пользовательские настройки в формате ключ=значение."""
    for name in ("package", "repository", "test_mode", "filter"):
        value = getattr(args, name)
        if isinstance(value, bool):
            value = str(value).lower()
        print(f"{name}={value}")


def main(argv=None):
    """Запустить прототип первого этапа и вернуть код завершения."""
    args = parse_args(argv)
    print_settings(args)
    return SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
