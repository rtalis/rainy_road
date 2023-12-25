# Rainy Road
## This script will show in a map if it is raining in a route between two cities.

###  It uses mainly **osmnx** (with networkx). You can get the app that uses this script as an server [here](https://github.com/rtalis/rainy-road-app/tree/main).


## Getting Started

You can download the project with: 
`git clone https://github.com/rtalis/rainy_road.git`

Go to the project folder and install all requirements with with `pip install -r requirements.txt`

You can run `flask run` inside the project folder and access it in http://127.0.0.1:5000/generate_map?start_location=CITYONENAME,STATE&end_location=CITYTWONAME,STATE or install [gunicorn](https://docs.gunicorn.org/en/stable/install.html) for a production enviroment.  

You can also try the [Rainy Road App](https://github.com/rtalis/rainy-road-app/tree/main), it uses this server as an backend.

## How it works
Set the names of the cities and a openwheather api key, it will find the shortest route between the places and show if it is raining on the road. The script uses osmnx to create a map, geopy for translate names to coordinates, networkx and scikit-learn for route, openweather for wheather data and folium to show it in a browser.


