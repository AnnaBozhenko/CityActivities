
## To load Telegram channel's posts:
* navigate to `app` dir
* add `tg_conn.ini` with filled:
```[TELEGRAM]
app_id=...
app_hash=...

``` 
*Sign in to Telegram developer account. (Mannual's)[https://docs.telethon.dev/en/stable/basic/signing-in.html] 
`Sign in` section may be helpful 
* flags to run `python telegram_scraper.py`:
    * `-u` - channel's username(s), e.g: `-u kyivmas dtek_ua`, str, required
    * `-y` - year of requested date, *int* **required**
    * `-m` - month of requested date, *int* **required**
    * `-d` - day's number of requested date, *int* **required**
    * `-l` - limit number of messages per eveery requested channel, *int*

Example to run request for `bbcukrainian` channel, 2026 yer, 2 month, 20 day, 2: 

```python telegram_scraper.py -u -y 2026 -m 2 -d 20```




