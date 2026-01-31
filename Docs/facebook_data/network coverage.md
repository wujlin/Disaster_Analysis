Network Coverage
Last updated August 10, 2022
Overview
Network Coverage maps show where Facebook users have cellular connectivity at a 2G, 3G or 4G connection type through their mobile device. This is determined based on the types of cell sites that users connect to in order to update their Facebook app’s data, which causes data to be sent between a user's device and the Facebook servers that host the app. In other words, this measures the estimated range, approximate coverage area and type of network connection based on the cell site IDs and locations that the users’ devices report. It is not based on data obtained from telecommunication services.


Questions the Network Coverage maps can help answer
•	Where do people have cellular connectivity?
•	Where did we not observe cellular connectivity throughout an area impacted by a disaster?
•	How certain are we that there has been a drop in cellular connectivity in an impacted area?


3 types of Network Coverage maps
Note: A cell site corresponds to an individual antenna, several of which a cell tower typically has. An antenna's physical characteristics determine its coverage area. For each cell site, we estimate its coverage area from the anonymized locations of users who have turned on the Location Services device setting on their mobile device and whose phones report being able to communicate with the cell site.
Active Network Coverage
This map shows which grid tiles in the region of interest had network coverage on that date. More precisely, we estimate which grid tiles had at least one cell site active on a given day. We assume a cell site is active on a day if we see at least one user pinging that cell site on that date.
Network Coverage Undetected
This map shows which grid tiles we are not certain of having network coverage on that date because no users’ devices reported connecting to cell sites there, but where we have observed coverage during the 30-day baseline period. We compare the maximum area where we observed some network coverage in the last 30 days, subtract the areas that had active coverage today and highlight the difference in this map.
Probability of Network Coverage
This map shows the probability of a grid tile receiving network coverage on that date based on our 30-day baseline observations. As not all cell sites receive traffic to Facebook’s servers on each day of the week, we calculate the likelihood of not observing network traffic on this cell site per day of the week and estimate how likely it is that the cell site is offline, given the expected amount of network traffic and the number of users estimated to be within its coverage area. This map complements the Network Coverage Undetected map by assigning a probability score to the grid tiles that we aren’t certain have network coverage on that date.


Data standards
Data aggregation: We publish this data in a grid format at Bing tile level 16. This is equivalent to roughly 600 meters on a side near the equator or the size of 2 city blocks.
We estimate if a grid tile lies inside the coverage areas of the nearby cell sites to determine if that tile is served by network coverage. To get the probability score of network coverage at a grid tile, we aggregate the independent probability scores attributed to all nearby cell sites serving that tile.
Cell site: We call a cell site an individual antenna or base station: The antenna's physical characteristics determine its coverage area, and it is identified by the unique IDs of the base station that controls the traffic going through it. A cell tower usually holds multiple such antennas.
Location signals: From users who have turned on the Location Services device setting on their mobile device, we collect and anonymize data on cell sites with which a phone reports it is able to exchange data.
Coverage area estimate: We weigh each location signal with the signal strength the phone reports for the cell site in question and calculate the weighted centroid as approximate cell site location.
Given this centroid, we calculate the 80th and 95th percentiles of distances of the location signals for the cell site. We define these distances as p80 and p95 radii. From these, we calculate the convex hull of all location signals that fall within these radii and output the corresponding polygons of the outline of this coverage area. We use the ratio of p80 and p95 radii as a quality metric for the estimate. If the p95 radius is much larger than the p80 radius, we can assume that the location signals for this cell site are probably impacted by artifacts caused by the phone’s API for location signals, and we filter those cell sites out of our coverage estimates.
Population sample: Only the data from Facebook users who have turned on the Location Services device setting on their mobile device contribute to these maps. In regions with few such users, estimates become more uncertain.
Data considerations: In areas affected by a crisis, it is very difficult to distinguish between a nonoperational cell site and one that didn't receive signals because users have left the area.
We rely on a phone's reporting of cell IDs, and we have found that different phone models occasionally report different cell IDs for the same physical base station. This leads to overcounting the number of cell sites covering a grid tile.
In addition, those incorrect cell IDs lead to fewer location samples for the correct cell ID and create additional unreliable coverage polygons for the incorrectly reported cell IDs. As we rely on “last known location” for our coverage area estimates, discrepancies between the actual location and the reported location of a user’s device may be included in the samples for any given cell site, especially when the cell site is close to an airport.
Codebook
These take the form human-friendly variable name (variable name in csv).
Coverage (coverage): 1 if we observed coverage for this grid cell. This variable is only in the Active Network Coverage dataset.
No coverage (no_coverage): 1 if we did not observe coverage for this grid cell. This variable is only in the Network Coverage Undetected dataset.
Probability of connectivity (p_connectivity): Probability of connectivity at this grid cell, given the expected network traffic for the day of the week and the expected number of users within the coverage area who have turned on the Location Services device setting on their mobile device. This variable is only in the Probability of Network Coverage dataset.
Latitude (lat): Latitude coordinate of the center of the Bing tile grid cell for the data point. The Presto geospatial library is used to generate this field.
Longitude (lon): Longitude coordinate of the center of the Bing tile grid cell for the data point. The Presto geospatial library is used to generate this field.
Country (country): The 2-letter abbreviation (ISO alpha-2 code) for the data point. The country value is assigned according to a tile’s intersection with country administrative boundaries derived from GADM.
Case studies
•	Red Cross: Humanitarian Needs: Food, water, and ... data?
More information about this dataset
•	Network Coverage maps overview
•	Facebook disaster maps helped Red Cross in Taal response, Philippine Star
•	Por qué la información en las redes sociales marca una diferencia en los desastres naturales, Brecha Cero

