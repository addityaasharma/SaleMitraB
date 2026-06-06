import random, secrets

def generateOTP_function():
    return str(secrets.randbelow(900000)+100000)

otp = generateOTP_function
print(otp)