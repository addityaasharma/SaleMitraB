from config.extension import celery
from functions.helper_function import *


@celery.task
def send_otp_task(email,otp):
    sendMail_function(email, otp)