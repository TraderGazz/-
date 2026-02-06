import sys
import requests
from map_scale import calculate_spn, calculate_map_center_and_spn, calculate_distance


def geocode_address(address):
    geocoder_api_server = "http://geocode-maps.yandex.ru/1.x/"
    geocoder_params = {
        "apikey": "8013b162-6b42-4997-9691-77b7074026e0",
        "geocode": address,
        "format": "json"
    }

    response = requests.get(geocoder_api_server, params=geocoder_params)

    if not response:
        return None

    json_response = response.json()
    toponym = json_response["response"]["GeoObjectCollection"]["featureMember"][0]["GeoObject"]
    toponym_coordinates = toponym["Point"]["pos"]
    toponym_address = toponym["metaDataProperty"]["GeocoderMetaData"]["text"]

    return {
        "coordinates": toponym_coordinates.split(" "),
        "address": toponym_address,
        "toponym": toponym
    }


def find_nearest_pharmacy(coordinates):
    search_api_server = "https://search-maps.yandex.ru/v1/"
    api_key = "dda3ddba-c9ea-4ead-9010-f43fbc15c6e3"

    search_params = {
        "apikey": api_key,
        "text": "аптека",
        "lang": "ru_RU",
        "ll": f"{coordinates[0]},{coordinates[1]}",
        "type": "biz",
        "results": 1
    }

    response = requests.get(search_api_server, params=search_params)

    if not response:
        return None

    json_response = response.json()

    if not json_response.get("features"):
        return None

    organization = json_response["features"][0]
    org_coordinates = organization["geometry"]["coordinates"]
    org_name = organization["properties"]["CompanyMetaData"]["name"]
    org_address = organization["properties"]["CompanyMetaData"]["address"]

    hours = "Нет информации"
    if "Hours" in organization["properties"]["CompanyMetaData"]:
        hours_text = organization["properties"]["CompanyMetaData"]["Hours"]["text"]
        hours = hours_text

    return {
        "coordinates": [str(org_coordinates[0]), str(org_coordinates[1])],
        "name": org_name,
        "address": org_address,
        "hours": hours
    }


def main():
    if len(sys.argv) < 2:
        print("Использование: python main.py 'адрес'")
        return

    address = " ".join(sys.argv[1:])

    address_data = geocode_address(address)
    if not address_data:
        print("Не удалось найти указанный адрес")
        return

    start_coords = address_data["coordinates"]
    start_address = address_data["address"]

    pharmacy_data = find_nearest_pharmacy(start_coords)
    print(pharmacy_data)
    if not pharmacy_data:
        print("Не удалось найти ближайшую аптеку")
        return

    pharmacy_coords = pharmacy_data["coordinates"]

    distance = calculate_distance(start_coords, pharmacy_coords)

    print("\n" + "=" * 50)
    print("РЕЗУЛЬТАТЫ ПОИСКА")
    print("=" * 50)
    print(f"Исходный адрес: {start_address}")
    print(f"Координаты: {start_coords[0]}, {start_coords[1]}")
    print("\nБлижайшая аптека:")
    print(f"Название: {pharmacy_data['name']}")
    print(f"Адрес: {pharmacy_data['address']}")
    print(f"Режим работы: {pharmacy_data['hours']}")
    print(f"Расстояние: {distance:.0f} метров ({distance / 1000:.2f} км)")
    print("=" * 50 + "\n")

    map_center, map_spn = calculate_map_center_and_spn(start_coords, pharmacy_coords)

    static_api_server = "https://static-maps.yandex.ru/v1"
    static_api_key = "f3a0fe3a-b07e-4840-a1da-06f18b2ddf13"

    points_param = f"{start_coords[0]},{start_coords[1]},pm2dgl~{pharmacy_coords[0]},{pharmacy_coords[1]},pm2gnm"

    static_params = {
        "apikey": static_api_key,
        "ll": map_center,
        "spn": map_spn,
        "l": "map",
        "pt": points_param
    }

    static_response = requests.get(static_api_server, params=static_params)

    if not static_response:
        print("Ошибка при получении карты")
        return

    map_file = "pharmacy_map.png"
    try:
        with open(map_file, "wb") as file:
            file.write(static_response.content)
        print(f"Карта успешно сохранена в файл '{map_file}'")
        print("На карте отмечены:")
        print(f"  • Исходная точка (красная метка): {start_address}")
        print(f"  • Аптека (синяя метка): {pharmacy_data['name']}")
    except IOError:
        print("Ошибка при сохранении файла")


if __name__ == "__main__":
    main()