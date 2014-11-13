#!/usr/bin/env python
#
# Indentation is 4 spaces.
#
# Available routes:
#
#   GET  /download/filehash
#   POST /upload
#   GET  /server-usage
#   GET  /disk-usage

import os
import codecs

from flask import Flask, render_template, request, g, jsonify, send_file, make_response, Response, stream_with_context
from werkzeug import secure_filename

from . import settings
from . import webcore_ as webcore
import file_encryptor

app = Flask(__name__)
app.config['TEMP_FOLDER'] = 'tmp'
app.config['MAX_CONTENT_LENGTH'] = settings.STORAGE_SIZE
app.config['METACHAINS_OVERRIDE'] = settings.METACHAINS_OVERRIDE

if not app.debug:
    import logging
    file_handler = logging.FileHandler('production.log')
    file_handler.setLevel(logging.WARNING)
    app.logger.addHandler(file_handler)


def get_webcore():
    wc = getattr(g, '_web_core', None)

    if wc is None:
        wc = g._web_core = webcore.WebCore()

    if settings.METACHAINS_OVERRIDE:
        wc.coin = settings.METACHAINS_OVERRIDE()
    return wc


@app.teardown_appcontext
def close_connection(exception):
    get_webcore().cloud.close()


#Upload post method to save files into directory
@app.route("/api/upload",methods=['POST'])
def upload():
    """Upload a file using cloud manager.

    This may take a while, as it uploads the given
    file to three different host providers (in parallel).

    """
    # Save the uploaded file into a temporary location.
    token       = request.form.get('token', None)
    file        = request.files['file']
    filename    = secure_filename(file.filename)
    temp_name   = os.path.join(app.config['TEMP_FOLDER'], filename)
    file.save(temp_name)

    try:
        receipt = get_webcore().charge_upload(token, temp_name)
        if receipt is None:
            response = make_response(jsonify(error='balance-insufficient'), 402)
        else:
            key = file_encryptor.convergence.encrypt_file_inline(temp_name, None)
            result = get_webcore().cloud.upload(temp_name)

            if not result:
                # Should we issue a refund?
                # get_webcore().refund(receipt)
                response = make_response(jsonify(error='upload-error'), 500)
            else:
                response = make_response(jsonify(filehash=result, key=codecs.encode(key, 'hex_codec')), 201)

        response.headers['Access-Control-Allow-Origin'] = 'http://localhost:8000'
        response.headers['Access-Control-Allow-Credentials'] = 'true'

        return response

    finally:
        os.remove(temp_name)


@app.route("/api/download/<filehash>",methods=['GET'])
def download(filehash):
    """Download a file from cloud manager.

    This may take a while, since the file may not
    be currently in local cache. If there is no
    file matching the given hash, returns a string
    with an error message.

    """
    cm = get_webcore().cloud

    key   = request.args.get('key', None)
    token = request.args.get('token', None)

    if not cm.exists(filehash):
        return jsonify(error='file-not-found'), 404

    receipt = get_webcore().charge_download(token, filehash)

    if receipt is None:
        return jsonify(error='balance-insufficient'), 402

    full_path = cm.warm_up(filehash)
    if full_path is None:
        get_webcore().refund(receipt)
        return jsonify(error='error-downloading-file'), 500

    if key is None:
        return send_file(full_path,
            attachment_filename=os.path.basename(full_path),
            as_attachment=True)
    else:
        decoded = codecs.decode(key, 'hex_codec')
        return Response(
            stream_with_context(
                file_encryptor.convergence.decrypt_generator(full_path, decoded)),
            mimetype="application/octet-stream",
            headers={"Content-Disposition":"attachment;filename=" + os.path.basename(full_path) })


@app.route("/api/find/<filehash>", methods=['GET'])
def find(filehash):
    cm = get_webcore().cloud

    info = cm.info(filehash)

    if info is None:
        return jsonify(error='File not found'), 404

    return jsonify(info)


@app.route("/api/status", methods=['GET'])
def status():
    """Return node status information.

    This includes transfer limits, storage usage,
    synchronization status and metachains status.

    """
    cm   = get_webcore().cloud
    coin = get_webcore().coin

    return jsonify({
        "bandwidth": {
            "total": {
                "incoming": cm.total_incoming(),
                "outgoing": cm.total_outgoing()
                },
            "current": {
                "incoming": cm.current_incoming(),
                "outgoing": cm.current_outgoing()
                },
            "limits": {
                "incoming": settings.TRANSFER_MAX_INCOMING,
                "outgoing": settings.TRANSFER_MAX_OUTGOING
                }
            },

        "storage": {
            "capacity": cm.capacity(),
            "used": cm.used_space(),
            "max_file_size": settings.STORAGE_FILE
            },

        "sync": {
            "cloud_queue": cm.upload_queue_info(),
            "blockchain_queue": cm.blockchain_queue_info()
            },

        "metachains": {
            "coin": 'florincoin',
            "balance": coin.balance(),
            "address": coin.address("incoming"),
            "block":   cm.last_known_block()
            }
        })

## Main
