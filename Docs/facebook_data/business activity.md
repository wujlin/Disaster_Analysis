Business Activity Trends During Crisis
Last updated November 4, 2022
Getting started
Business Activity Trends During Crisis uses data about posting activity on Facebook to measure how local businesses are affected by and recover from crisis events. Given the broad presence of small businesses on the Facebook platform, this dataset aims to provide timely estimates of global business activity without the common limitations of traditional data collection methods, such as scale, speed and nonstandardization. This method for understanding local economic activity, first described by the University of Bristol team and published in Nature Communications, is intended to provide humanitarian organizations, researchers and policymakers with a broad view of subnational economic activity after disasters.
When these maps are generated
The Facebook app’s Safety Check feature triggers creation of the maps, which cover only the areas affected by a crisis event. This dataset is generated for each area and time experiencing a crisis. Partners are also welcome to request dataset generation.
How we measure business activity
A separate Business Activity Trends dataset is produced for each crisis event. Business activity is measured by the volume of posts made by business Pages on Facebook on a daily basis, where a post is defined broadly to include posts, stories and reels created by the business Page anywhere on Facebook. In practice, almost all posts are either made on the business Page itself or in Facebook Groups.
For each crisis event, a baseline posting pattern is established using the 90 days prior to the event start date. We then measure the daily posting activity relative to the expected posting activity based on the baseline period. Individual business Page activity is then aggregated by business vertical (proxy for economic sector) and by GADM administrative polygons geographically. For most crises, the crisis location is defined by a geographic bounding box, and data are produced at the US county-equivalent level (GADM 2) within the bounding box, although the level may differ by country. Each cell (row) of the dataset contains data on the daily activity within a polygon-vertical combination.
Questions the dataset helps answer
•	How quickly are different sectors of the local economy recovering after a natural disaster?
•	Which geographic areas affected by a natural disaster experienced the most negative economic impact?
Features of Business Activity Trends During Crisis
•	Updated daily wherever there are enough business Pages to ensure privacy
•	Built using a standard methodology for the entire globe
•	Disaggregated metrics available for 10+ economic sectors
•	Available to download in csv format for analysis
Codebook
•	Polygon ID (polygon_id): Unique identifier from theDatabase of Global Administrative Areas (GADM) for the polygon representing the region or administrative area
•	Polygon name (polygon_name): Name of the polygon based on theDatabase of Global Administrative Areas (GADM)
•	Polygon level (polygon_level): Administrative level of the administrative region as defined in the Database of Global Administrative Areas (GADM). Using the United States as an example:
GADM0=country (United States)
GADM1=state (Florida)
GADM2=county (Dade County)
•	Polygon version (polygon_version): Version of the Database of Global Administrative Areas (GADM) used
•	Country (country): The 2-letter abbreviation (ISO alpha-2 code) for the data point. The country value is assigned according to theDatabase of Global Administrative Areas (GADM) defining country boundaries.
•	Business vertical (business_vertical): The business category of the aggregation. Business verticals are defined internally within Facebook by categories selected by the Page admins. We use business verticals as a proxy for local economic sectors. Included as a business vertical is the category all, which includes all other business verticals except public good.
•	Activity quantile (activity_quantile): The level of activity as a quantile relative to the baseline period. This is equivalent to the 7-day average of what University of Bristol researchers call the aggregated probability integral transform metric (see this article in Nature Communications). It’s calculated by first computing the approximate quantiles (the midquantiles in the article) of each Page’s daily activity relative to their baseline activity. The quantiles are summed and the sum is then shifted, rescaled and variance-adjusted to follow a standard normal distribution. The adjusted sum is then probability transformed through a standard normal cumulative distribution function to get a value between 0 and 1. We then average this value over the last 7 days to smooth out daily fluctuations. We give this metric a quantile interpretation since it compares the daily activity to the distribution of daily activity within the baseline period, where a value around 0.5 is considered normal activity. This is a one-vote-per-Page metric that gives equal weight to all businesses and is not heavily influenced by businesses that post a lot.
•	Latitude (latitude): Latitude coordinate of the center of the boundary polygon shape for the administrative region
•	Longitude (longitude): Longitude coordinate of the center of the boundary polygon shape for the administrative region
•	Date (ds): The date in Pacific Time (PT) for which the data is being reported
Business verticals
We derived the business verticals by aggregating categories as defined by the admins on the business Pages.
•	All: Refers to all businesses in the polygon. This includes all of the following categories except public good, because the activity of public good Pages tends to differ from other businesses during crises.
•	Grocery and convenience stores: Retailers that sell everyday consumable goods including food (typically unprepared foods and ingredients) and a limited range of household goods (like toilet paper). These can include grocery stores, convenience stores, pharmacies and general stores.
•	Retail: Retail other than grocery and convenience stores such as auto dealers, home goods stores, personal goods stores and general merchandise/big-box stores like Walmart
•	Restaurants: Businesses that sell prepared food and beverages for on-premise or off-premise dining
•	Localevents: Events, activities and businesses that sell real-life experiences, such as amusement parks, bowling alleys, concert venues and social clubs
•	Professional services: Services driven by demand from an individual event such as a legal need or health issue that require high customization. Providers usually have an advanced degree or certification and are considered experts and “knowledge workers.” Examples include CPAs, lawyers, medical professionals, architects.
•	Business and utility services: Business offering business-to-business services like construction, office cleaning, advertising and marketing, and business software solutions. Utility services offer commodity services like electric, phone, internet, water and energy.
•	Home services: Services driven by demand from an individual event at home such as plumbing or electrical work. Examples include home repairs, photographers, cleaning, mechanics, plumbers, electricians, landscapers, interior decorators.
•	Lifestyle services: Specific to beauty, care and fitness services. These businesses offer standardized services that are part of a customer's regular routines. Examples include gyms, salons, barbers, and nonmedical and noneducational supervision, like childcare nurseries and pet care.
•	Travel: Businesses that provide or sell transportation or accommodation services, such as airlines, hotels, car rentals and tour operators
•	Manufacturing: Businesses that manufacture durable goods (like furniture and cars) or consumable goods (like food and personal goods) and have no or limited business-to-customer sales
•	Public good: Includes government agencies, nonprofits and religious organizations
Data standards
•	Population sample: The Business Activity Trends During Crisis dataset uses a static sample of businesses’ Facebook Pages for each crisis defined at each crisis date. It does not take into account new Pages businesses created during the crisis, nor does it exclude Pages removed during the crisis. The sample for each crisis is defined as Facebook Pages that meet the following criteria:
•	Have an admin
•	Have monthly activity as of the crisis start date
•	Were created at least 90 days prior to the crisis start date
•	List a physical location
•	Are associated with a business as defined by internal business Page classifiers
•	Represent a local business according to business vertical categories (which excludes large companies, for example)
•	Pass Facebook’s internal quality control measures such as filtering for spam and duplicate Pages
•	Spatial aggregation: Business Activity Trends During Crisis is aggregated to country, US state-equivalent, and US county-equivalent administrative boundaries. We use the territorial boundaries and names provided by the GADM project.
•	Temporal aggregation: We update Business Activity Trends During Crisis daily. The metrics are reported for posting activity that took place during the 24-hour period defined by the date value.
•	Business vertical aggregation: We aggregate data by business verticals defined internally as a proxy for the economic sector. We include as a vertical all, which is a superset of all other business verticals except public good.
•	Minimum counts: Polygons and business verticals with fewer than 10 active business Pages that meet the sampling criteria are excluded from the dataset for privacy protection.
•	File format: Data is provided in the format of a global comma-delimited text file, GeoJSON or Mbtiles.
More information about this dataset
•	Facebook Business Activity Trends overview
Case studies and publications
•	Nature Communications article by the University of Bristol team
•	Methodology white paper (with all the technical details)

