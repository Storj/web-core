web-core
========
[![Build Status](https://travis-ci.org/Storj/web-core.svg?branch=master)](https://travis-ci.org/Storj/web-core)
[![Coverage Status](https://coveralls.io/repos/Storj/web-core/badge.png?branch=master)](https://coveralls.io/r/Storj/web-core?branch=master) 

web-core, a filehost web app, that allows anyone to upload files via an API.
Files are hashed and uploaded to public file hosting. Using the hashes a node
can look up the information of where that file was stored using the
[Florincoin](http://florincoin.info/) blockchain. This makes a file uploaded to
MetaDisk accessible through any node in the network.

- Coded in [Python](http://python.org/) and [Flask](http://flask.pocoo.org/), a Python microframework for web.
- Must be run on a Linux based web server, [Debian](http://www.debian.org/) distro recommended.

#### Web interface

If you wish to use this in a browser, take a look at
[MetaDisk](https://github.com/Storj/Metadisk). It is a web interface,
composed of only html, css and javascript, powered by the web-core API.


#### Scope

This project depends on several other projects:

- [plowshare-wrapper](https://github.com/Storj/plowshare-wrapper) provides a
  python interface to upload and download files from popular file hosting
  sites. It is a python wrapper of the plowshare tool.

- [cloud-manager](https://github.com/Storj/cloud-manager) contains most of the
  file handling logic. It keeps track of all the uploaded files, keeps track of
  the files present in local cache, and handles database serialization.

- [metachains-dtc](https://github.com/Storj/metachains-dtc) is a wrapper for
  the Florincoin client, using json RPC. It also contains a synchronization class,
  which allows one to synchronize data from and to the blockchain.

- [file-encryptor](https://github.com/Storj/file-encryptor) is an encryption
  package that implements convergent encryption using HMAC-SHA256 and AES128-CTR.

This project puts everything together and makes it accessible through a web
application. It uses `cloudmanager` to manage all uploads/downloads, and
`metachains-dtc` to enable synchronization of the hosted content information
between nodes running MetaDisk. All uploaded files are encrypted using
`file-encryptor`.


#### Synchronization note

Keep in mind that the `upload` command spends Florincoins, so be careful when
using it.

#### Transfer cost

Each time you upload or download a file, credit is removed from your account.
The credited values vary wether you are uploading or downloading a file, and
if the file is already present on the server or not.

Uploading a file of B bytes will cost you ```4 * B``` bytes of credit. One
time for the upload transfer and three times for the cloud hosting transfer.

Downloading a file of B bytes will cost you ```2 * B``` bytes of credit if the
file is not on the server's local cache. If it is, this value will be reduced
to ```B``` bytes of credit.


## Installation

Check [INSTALL.md](INSTALL.md) for installation instructions.


## API documentation

Upload a file to the cloud manager:

    POST /api/upload
    Parameters:
    - file


Download a file from the cloud manager identified by the given file hash:

    GET /api/download/<filehash>
    Parameters:
    - filehash


Retrieve information regarding a given file hash:

    GET /api/find/<filehash>
    Parameters:
    - filehash

    Error results:
    { "error": "File not found" }

    Normal result:
    {
        "datetime": "1398875062",
        "filehash": "b17fee6427ee665eb54159762fe03847792af1d94bf6769b82f95b95e82975d2",
        "filename": "b17fee6_WhatisStorj.pdf",
        "filesize": 337748,
        "uploads": [
            {
                "host_name": "ge_tt",
                "url": "http://ge.tt/162T7Ef1/v/0"
            },
            {
                "host_name": "gfile_ru",
                "url": "http://gfile.ru/a4WfC"
            },
            {
                "host_name": "rghost",
                "url": "http://rghost.net/54761561"
            }
        ],
        "version": "0.2"
    }


Retrieve node information, including storage, transfer limits, synchronization
status, florincoin information. All sizes are in bytes.

    GET /api/status
    Parameters: None

    Normal result:
        {
            "bandwidth": {
                "total": {
                    "incoming": 792431,
                    "outgoing": 953218
                    },
                "current": {
                    "incoming": 192746,
                    "outgoing": 547291
                    },
                "limits": {
                    "incoming": 1048576,
                    "outgoing": 2097152
                    }
                },

            "storage": {
                "capacity":      67108864,
                "used":          5909746,
                "max_file_size": 1048576
                },

            "sync": {
                "blockchain_queue": {
                    "count": 73,
                    "size":  912834
                },
                "cloud_queue": {
                    "count": 12,
                    "size":  6572
                },

            "datacoin": {
                "balance": 1.05,
                "address": "DPhb7Pe1Ur6nWzLYBC1SeV8xAGCrYGMLVn"
                }
        }


## Token API Documentation

### Public API (doesn't require authentication)

Generate a new access token:

    POST /accounts/token/new
    Parameters: None

    Normal result:
    {
        "token": "adF7WFCpQR2EvFkG"
    }


Retrieve node bandwidth prices:

    GET /accounts/token/prices
    Parameters: None

    Normal result:
    {
        "prices": [
            { "amount": 107374182400,  "cost": 500  },
            { "amount": 1073741824000, "cost": 5000 }
        ]
    }


Retrieve the transfer byte balance for a given access token:

    GET /accounts/token/balance/<access_token>
    Parameters: None

    Normal result:
    {
        "balance": 1675029880
    }


Redeem a promocode for the given access token:

    POST /accounts/token/redeem/<access_token>
    Parameters:
    - promocode

    Error results:
    { "status": "error" }

    Normal result:
    { "status": "ok" }


### Private API (requires authentication)

Deposits the given amount of bytes to the given access token:

    POST /accounts/token/deposit/<access_token>
    Parameters:
    - bytes

    Headers:
    - Authentication: <SECRET_KEY>

    Error results:
    { "status": "invalid-authentication" }
    { "status": "bad-request" }

    Normal result:
    { "status": "ok" }


Withdraws the given amount of bytes from the given access token:

    POST /accounts/token/withdraw/<access_token>
    Parameters:
    - bytes

    Headers:
    - Authentication: <SECRET_KEY>

    Error results:
    { "status": "invalid-authentication" }
    { "status" : "bad-request" }
    { "status" : "balance-insufficient"}

    Normal result:
    { "status": "ok" }

