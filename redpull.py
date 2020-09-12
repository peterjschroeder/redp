#!/usr/bin/python3
import configparser, contextlib, csv, datetime, gallery_dl, io, logging, mailbox, os, pidfile, praw, re, shutil, sys, tempfile, time, urllib, youtube_dl
from archivenow import archivenow
from email.headerregistry import Address
from email.message import EmailMessage
from email.mime.text import MIMEText
from natsort import humansorted
from psaw import PushshiftAPI
from urllib.request import urlopen, urlparse, Request
from xdg.BaseDirectory import *

# Configuration
os.makedirs(os.path.join(xdg_config_home, "redp"), exist_ok=True)
config_defaults_redp = {
        'reddit_client_id': '',
        'reddit_client_secret': '',
        'reddit_username': '',
        'reddit_password': '',
        'path_maildir': '~/Mail/Reddit',
        }

config_defaults_redpull = {
        'skip_automoderator': 'no',
        'autoquote': 'no',
        'attachments': 'image,text',
        'attachments_max_size': '10000',
        'archive': 'no',
        'expire': 'no'
        }

config = configparser.ConfigParser()

if os.path.exists(os.path.join(xdg_config_home, 'redp/config')):
    config.read(os.path.join(xdg_config_home, 'redp/config'))

    # Check for missing keys
    for i in config_defaults_redp:
        if not config.has_option('redp', i):
            config['redp'][i] = config_defaults_redp[i]
    for i in config_defaults_redpull:
        if not config.has_option('redpull', i):
            config['redpull'][i] = config_defaults_redpull[i]
    with open(os.path.join(xdg_config_home, 'redp/config'), 'w') as configfile:
        config.write(configfile)

    reddit_client_id = config['redp']['reddit_client_id']
    reddit_client_secret = config['redp']['reddit_client_secret']
    reddit_username = config['redp']['reddit_username']
    reddit_password = config['redp']['reddit_password']
    path_maildir = os.path.expanduser(config['redp']['path_maildir'])

    skip_automoderator = os.path.expanduser(config['redpull']['skip_automoderator'])
    autoquote = os.path.expanduser(config['redpull']['autoquote'])
    attachments = config['redpull']['attachments']
    attachment_max_size = config['redpull']['attachments_max_size']
    archive = config['redpull']['archive']
    expire = config['redpull']['expire']
else:
    print("Creating config file. Modify as needed before running again.")

    config.add_section('redp')
    config.add_section('redpull')

    for i in config_defaults_redp:
        config['redp'][i] = config_defaults_redp[i]
    for i in config_defaults_redpull:
        config['redpull'][i] = config_defaults_redpull[i]

    with open(os.path.join(xdg_config_home, 'redp/config'), 'w') as configfile:
        config.write(configfile)

    exit()

# API Setup
reddit = praw.Reddit(client_id=reddit_client_id, client_secret=reddit_client_secret, password=reddit_password, user_agent='redp by /u/peterjschroeder github.com/peterjschroeder/redp', username=reddit_username)

api = PushshiftAPI(reddit)

# Logging
os.makedirs(os.path.join(xdg_cache_home, 'redp'), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%m/%d/%Y %H:%M:%S",
    handlers=[
        logging.FileHandler(os.path.join(xdg_cache_home, 'redp/redpull.log')),
        logging.StreamHandler()
    ]
)

logging.getLogger("archivenow").setLevel(logging.ERROR)
logging.getLogger("psaw").setLevel(logging.ERROR)

def get_subscriptions():
    subscribed = []

    if not os.path.exists(os.path.join(xdg_config_home, "redp/subscribed")):
        logging.warning('Run "redpick" first to create a subscriptions file.')
        exit()

    with open(os.path.join(xdg_config_home, "redp/subscribed")) as f:
        subscriptions = csv.reader(f, delimiter='\t')
        for i in subscriptions:
            subscribed.append(i)
    f.close()

    return subscribed

def get_numcomments(submission):
    if not os.path.exists('%s/%s/.numcomments' % (path_maildir, submission.subreddit)):
        return 0
    else:
        count = 0

        with open('%s/%s/.numcomments' % (path_maildir, submission.subreddit)) as f:
            reader = csv.reader(f, delimiter='\t')
            for i in reader:
                if i[0] == submission.id:
                    count = int(i[1])
        f.close()

        if os.path.exists('%s/%s/.skipped' % (path_maildir, submission.subreddit)):
            with open('%s/%s/.skipped' % (path_maildir, submission.subreddit)) as f:
                reader = csv.reader(f, delimiter='\t')
                for i in reader:
                    if i[0] == submission.id:
                        count += int(i[1])
            f.close()

        return count

    return 0

def write_numcomments(submission, numcomments):
    reader = []

    if os.path.exists('%s/%s/.numcomments' % (path_maildir, submission.subreddit)):
        reader = list(csv.reader(open('%s/%s/.numcomments' % (path_maildir, submission.subreddit)), 
            delimiter='\t'))

    with open('%s/%s/.numcomments' % (path_maildir, submission.subreddit), 'w') as f:
        writer = csv.writer(f, delimiter='\t')

        for i in reader:
            if i[0] != submission.id:
                writer.writerow([i[0], i[1]])

        writer.writerow([submission.id, numcomments])

def get_retrieved(subscription):
    if not os.path.exists('%s/%s/.retrieved' % (path_maildir, subscription)):
        retrieved = []
    else:
        l = open('%s/%s/.retrieved' % (path_maildir, subscription), 'r+', encoding='utf-8')
        retrieved = l.read().splitlines()
        l.close()

    return retrieved

def write_retrieved(subscription, message):
    l = open('%s/%s/.retrieved' % (path_maildir, subscription), 'a', encoding='utf-8')
    l.write("%s\n" % message)
    l.close()

def write_skipped(subscription, message):
    l = open('%s/%s/.skipped' % (path_maildir, subscription), 'a', encoding='utf-8')
    l.write("%s\n" % message)
    l.close()

def quote_message(submission, comment):
    quote = ""

    if autoquote == "no" or comment.parent().id == submission.id:
        return quote

    quote_comments = []

    while comment.parent().id != submission.id:
        quote_comments.append(comment.parent())
        comment = comment.parent()

    quote_list = []

    for i in range(0, len(quote_comments)):
        quote = "%s\n\n" % (re.sub('^', (">" * (i+1)) + " ", "%s wrote:\n%s" % (quote_comments[i].author, quote_comments[i].body), flags=re.M)) + quote

    return quote

def get_submissions(subreddit, use_pushshift):
    logging.info("Fetching submissions for %s." % subreddit[0])
    retrieved = get_retrieved(subreddit[0])

    if use_pushshift:
        for j in set(list(api.search_submissions(after=int(float(subreddit[1])), subreddit=subreddit[0], limit=None))):
            write_messages(j, retrieved, int(float(subreddit[1])), int(subreddit[2]), 
                    int(subreddit[3]), int(subreddit[4])*86400, False)
    else:
        for j in set(list(reddit.subreddit(subreddit[0]).new(limit=100)) +
                list(reddit.subreddit(subreddit[0]).controversial(limit=100)) +
                list(reddit.subreddit(subreddit[0]).rising(limit=100)) +
                list(reddit.subreddit(subreddit[0]).hot(limit=100)) +
                list(reddit.subreddit(subreddit[0]).top("all"))):
            write_messages(j, retrieved, int(float(subreddit[1])), int(subreddit[2]), 
                    int(subreddit[3]), int(subreddit[4])*86400, True)

def write_messages(submission, retrieved, max_age, minimum_comments, minimum_score, expiration, private):
    # Create directories if they do not exist
    os.makedirs("%s/%s/cur" % (path_maildir, submission.subreddit), exist_ok=True)
    os.makedirs("%s/%s/new" % (path_maildir, submission.subreddit), exist_ok=True)
    os.makedirs("%s/%s/tmp" % (path_maildir, submission.subreddit), exist_ok=True)

    # Bail out totally under certain conditions so as to not check comments
    if ((submission.num_comments < minimum_comments) or (submission.score < minimum_score) or (float(submission.created_utc) < max_age) or 
            (float(submission.created_utc) < expiration)):
        return

    # Write submission
    if (submission.id not in retrieved):
        logging.info("%s: Retrieving submission %s." % (submission.subreddit, submission.id))
        f = open('%s/%s/new/%s' % (path_maildir, submission.subreddit, submission.id), 'wb')
        msg = EmailMessage()
        msg['From'] = Address(submission.author.name if submission.author else "deleted", submission.author.name if submission.author else "deleted", "reddit.com")
        msg['Subject'] = submission.title
        msg['Date'] = datetime.datetime.utcfromtimestamp(submission.created_utc).strftime("%a, %d %b %Y %H:%M:00")
        msg['Message-ID'] = "<%s@reddit.com>" % submission.id
        msg['Content-Location'] = submission.permalink

        if submission.is_self:
            msg.set_content("%s" % submission.selftext)
        # Nonsense check because reddit allow /r/comments/... in the url field
        elif not urlparse(submission.url).scheme:
            msg.set_content("%s" % submission.url)
        # Try to add the url's content as attachments.
        elif not get_attachment(submission.url, msg):
            msg.set_content("%s" % submission.url)
            # Archive the url for later use
            if archive == 'yes':
                logging.info("%s: Archiving %s." % (submission.subreddit, submission.url))
                with contextlib.redirect_stdout(io.StringIO()):
                    archivenow.push(submission.url,"ia")

        f.write(bytes(msg))
        f.close()
        write_retrieved(submission.subreddit, submission.id)

    # Don't look for comments if we already have more or equal to
    if get_numcomments(submission) >= submission.num_comments:
        return

    # Write comments
    if private:
        submission.comments.replace_more(limit=None)
        comments = submission.comments.list()
    else:
        comments = api.search_comments(after=max_age, subreddit=submission.subreddit, submission_id=submission.id, limit=None)

    numcomments = get_numcomments(submission)

    for comment in comments:
        # Check for new comments
        if (comment.id in retrieved):
            continue

        if ((float(comment.created_utc) < max_age) or
                (float(comment.created_utc) < expiration) or 
                (comment.author and comment.author.name == 'AutoModerator')):
            write_skipped(submission.subreddit, comment.id)
            continue
        logging.info("%s: Retrieving comment %s." %  (submission.subreddit, comment.id))
        f = open('%s/%s/new/%s' % (path_maildir, submission.subreddit, comment.id), 'wb')
        msg = EmailMessage()
        msg['From'] = Address(comment.author.name if comment.author else "deleted", comment.author.name if comment.author else "deleted", "reddit.com")
        msg['Subject'] = submission.title
        msg['Date'] = datetime.datetime.utcfromtimestamp(comment.created_utc).strftime("%a, %d %b %Y %H:%M:00")
        msg['References'] = "<%s@reddit.com>%s" % (submission.id, '' if comment.parent() == submission.id else ' <%s@reddit.com>' % comment.parent())
        msg['In-Reply-To'] = "<%s@reddit.com>" % comment.parent()
        msg['Message-ID'] = "<%s@reddit.com>" % comment.id
        msg['Content-Location'] = comment.permalink
        msg.set_content("%s%s" % (quote_message(submission, comment), comment.body))
        f.write(bytes(msg))
        f.close()
        write_retrieved(submission.subreddit, comment.id)
        numcomments += 1
    # Done outside the loop to avoid tons of read/writes.
    # Drawback is, if the loop is interupted, the new count isn't stored which will cause a recheck even if we have all the comments.
    write_numcomments(submission, numcomments)

def get_attachment(url, msg):
    # Image galleries
    if 'all' in attachments or 'image' in attachments:
        if gallery_dl.extractor.find(url):
            dir_download = tempfile.mkdtemp()
            gallery_dl.config.load()
            gallery_dl.config.set(('extractor',), "directory", "")
            gallery_dl.config.set(('extractor',), "base-directory", dir_download)
            gallery_dl.config.set(('output',), 'mode', 'null')
            gallery_dl.job.DownloadJob(url).run()

            images = os.listdir(dir_download)
            if len(images) > 0:
                for i in images:
                    with open(os.path.join(dir_download, i), 'rb') as f:
                        imgfile = f.read()
                    msg.add_attachment(imgfile, maintype="image", subtype=os.path.splitext(f.name)[1])
                shutil.rmtree(dir_download)
                return True

    # Videos
    if 'all' in attachments or 'video' in attachments:
        extractors = youtube_dl.extractor.gen_extractors()
        for e in extractors:
            if e.suitable(url) and e.IE_NAME != 'generic':
                dir_download = tempfile.mkdtemp()
                ydl_opts = {'match_filter': youtube_dl.utils.match_filter_func("!is_live"), 'noplaylist': True, 'no_warnings': True, 'outtmpl': dir_download+'/%(title)s.%(ext)s', 'quiet': True,}
                ydl = youtube_dl.YoutubeDL(ydl_opts)

                try:
                    ydl.download([url])
                except Exception:
                    return False
                    
                videos = os.listdir(dir_download)
                if len(videos) > 0:
                    for i in videos:
                        with open(os.path.join(dir_download, i), 'rb') as f:
                            video = f.read()
                        msg.add_attachment(video, maintype="video", subtype=os.path.splitext(f.name)[1])
                    shutil.rmtree(dir_download)
                    return True

    # Everything else
    try:
        # Reddit thinks it's cute allowing unicode in urls
        response = urlopen(Request(url.encode('ascii', errors='ignore').decode(), 
            headers={'User-Agent': 'Mozilla/5.0'}), timeout=10)
    except urllib.error.HTTPError as e:
        # FIXME: Handle this with wayback machine.
        if e.code == 404:
            return False
        else:
            return False
    except Exception:
        return False

    info = response.info()
    imgdata = response.read()

    exclude_mimetypes = ["application/x-httpd-php", "text/asp", "text/css", "text/html", "text/javascript"]
    if info.get_content_maintype() in attachments and info.get_content_type() not in exclude_mimetypes:
        msg.add_attachment(imgdata, maintype=info.get_content_maintype(), subtype=info.get_content_subtype(), 
        filename=re.findall("filename=(.+)", r.headers["Content-Disposition"])[0] 
        if "Content-Disposition" in response.headers.keys() else url.split("/")[-1])
        return True

    return False

def remove_expired_messages(subscribed):
    logging.info("Removing expired messages.")

    for i in subscribed:
        maildir = mailbox.Maildir("%s/%s" % (path_maildir, i[0]))
        submissions = []
        to_remove = []

        try:
            # Run through the loop twice so we can remove all comments for an expired submission.
            for key, msg in maildir.iteritems():
                if datetime.datetime.strptime(msg['Date'], "%a, %d %b %Y %H:%M:00 -0000").timestamp() < time.time() - (int(i[4])*86400) and not msg['References']:
                    submissions.append(msg['Message-ID'])
                    to_remove.append(key)
            for key, msg in maildir.iteritems():
                if msg['References'] and msg['References'].split(' ')[0] in submissions:
                    to_remove.append(key)
            maildir.lock()
            try:
                for key in to_remove:
                    logging.info("%s Removing %s." % (i[0], key))
                    maildir.remove(key)
            finally:
                maildir.flush()
                maildir.close()
        except:
            continue

def main():
    try:
        with pidfile.PIDFile(os.path.join(xdg_cache_home, 'redp/redpull.pid')):
            force_praw = False

            if len(sys.argv) > 1:
                if str(sys.argv[1]) == "--quiet":
                    logging.getLogger().removeHandler(logging.getLogger().handlers[1])
                elif str(sys.argv[1]) == "--force-praw":
                    force_praw = True

            subscribed = get_subscriptions()

            if expire == 'yes':
                remove_expired_messages(subscribed)

            for i in subscribed:
                if reddit.subreddit(i[0]).subreddit_type == "private" or force_praw:
                    get_submissions(i, False)
                else:
                    get_submissions(i, True)

    except pidfile.AlreadyRunningError:
        logging.error('redpull is already running.')

if __name__ == "__main__":
    main()
