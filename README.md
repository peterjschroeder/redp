![Preview](https://user-images.githubusercontent.com/10292399/95669527-c3c93f00-0b4f-11eb-80a3-75e3205a0c27.png)

# redp
**Install**\
pip3 install git+https://github.com/peterjschroeder/redp

**Create an api key**\
Go to https://www.reddit.com/prefs/apps/ \
Create another app \
Select script \
Name it something \
Put something in the redirect url ex:https://github.com/peterjschroeder/redp

**Config**\
Run redpick or redpull.py to create the default config.
edit ~/.config/redp/config\
Fill in reddit_username and reddit_password\
client_secret is the secret on the apps page\
client_id is under personal use script on the apps page\
redpick.py\
redpull.py\
Add to crontab. Example: @hourly redpull.py --quiet\
\
**Mutt**\
folder-hook Reddit " \\\
        set     from='your@email.com' \\\
                sendmail = "/usr/local/bin/redpush.py"

unmailboxes *\
mailboxes = \`echo -n "= "; find ~/Mail/ -mindepth 2 -maxdepth 3 -type d -name "*" -printf "'%h' \`\
unmailboxes ~/Mail/
