import sys
import requests
from map_scale import calculate_spn


def main():
    toponym_to_find = " ".join(sys.argv[1:])
    if not toponym_to_find:
        print("Введите адрес для поиска")
        return

    geocoder_api_server = "http://geocode-maps.yandex.ru/1.x/"
    geocoder_params = {
        "apikey": "8013b162-6b42-4997-9691-77b7074026e0",
        "geocode": toponym_to_find,
        "format": "json"
    }

    response = requests.get(geocoder_api_server, params=geocoder_params)

    if not response:
        print("Ошибка выполнения запроса к Geocoder API")
        return

    json_response = response.json()

    toponym = json_response["response"]["GeoObjectCollection"]["featureMember"][0]["GeoObject"]
    toponym_coordinates = toponym["Point"]["pos"]
    toponym_longitude, toponym_latitude = toponym_coordinates.split(" ")

    spn = calculate_spn(toponym)

    static_api_server = "https://static-maps.yandex.ru/v1"
    static_api_key = "f3a0fe3a-b07e-4840-a1da-06f18b2ddf13"

    static_params = {
        "apikey": static_api_key,
        "ll": f"{toponym_longitude},{toponym_latitude}",
        "spn": spn,
        "l": "map",
        "pt": f"{toponym_longitude},{toponym_latitude},pm2dgl"
    }

    static_response = requests.get(static_api_server, params=static_params)
    print(static_response)

    if not static_response:
        print("Ошибка выполнения запроса к Static API")
        return

    map_file = "map.png"
    try:
        with open(map_file, "wb") as file:
            file.write(static_response.content)
        print(f"Карта успешно сохранена в файл '{map_file}'")
        print(f"Координаты: {toponym_longitude}, {toponym_latitude}")
        print(f"Размеры объекта (spn): {spn}")
    except IOError:
        print("Ошибка при сохранении файла")


if __name__ == "__main__":
    main()