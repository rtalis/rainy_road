# rainy_road
## This script will show in a map if it is raining in a route between two cities.

### You will need **osmnx** (includes networkx), **geopy**, **scikit-learn** and **folium**. You can install them with `pip`

Set the names of the cities and a openwheather api key, it will find the shortest route between the places and show if it is raining on the road. The script uses osmnx to create a map, geopy for translate names to coordinates, networkx and scikit-learn for route, openweather for wheather data and folium to show it in a browser.


