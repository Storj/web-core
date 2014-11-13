#!/usr/bin/env python
# Daemon to synchronize all parts:
# - send local storage to cloud hosting websites
# - fetch metadata from blockchain
# - send new local metadata to blockchain

import time
import settings
import cloudmanager
import metachains
import logging

def make_cloudmanager():
    return cloudmanager.CloudManager(
        settings.DATABASE_PATH,
        settings.STORAGE_PATH,
        settings.STORAGE_SIZE)

def make_coin():
    return metachains.Florincoin(
        settings.METACHAINS_URL,
        settings.METACHAINS_USERNAME,
        settings.METACHAINS_PASSWORD)

def make_sync(coin, cloud):
    return metachains.Synchronizer(
        coin,
        cloud)


if __name__ == "__main__":
    coin  = make_coin()
    cloud = make_cloudmanager()
    sync  = make_sync(coin, cloud)
    log_config = { #TODO: syslog on WARN or above
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
            },
        },
        'handlers': {
            'default': {
                'level':'INFO',    
                'class':'logging.StreamHandler',
            },  
        },
        'loggers': {
            'storj.cloudmanager': {                  
                'handlers': ['default', ],
                'level': 'INFO',  
                'propagate': True,
            },
        }
    }
    logging.config.dictConfig(log_config)
    log = logging.getLogger('cloudsync')

    while True:
        sync.scan_blockchain()
        sync.scan_database()
        cloud.cloud_sync()

        log.info('Completed sync iter, sleeping...') # TODO make debug
        time.sleep(settings.CLOUDSYNC_WAIT)
