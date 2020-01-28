# SCALP BOT

Implementation of buy cheap - sell expensive algorithm with some advanced features.  

----------------
For now this code is not in working shape - needed to add some functions in order to migrate to ZTOM. 
So more as a kind of a reference code and algo implementation example... 
----------------
  
Features:   
   - could work in opposite way sell expensive - buy cheaper (shorting)
   - try to detect trends by moving average
   - bids "ladder" inside order book
   - reporting to influxDb
   - offline mode (dry run): --offline cli option

Algo excel model: https://docs.google.com/spreadsheets/d/1xuw9KfADscfIW0llWDLKmLjUrPKTtct4eCuLZzDLIGQ/edit?usp=sharing

Usage: 
- offline mode 
    ```bash
    python3 scalp.py --offline
    ```

Could conduct real trades!!!

Use it at your own risk!!!!

   
   
   
  