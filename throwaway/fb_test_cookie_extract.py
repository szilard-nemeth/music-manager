import os
import sqlite3
import sys
from os.path import expanduser

from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2

### BASED ON THIS SO ANSWER: https://stackoverflow.com/a/56936539/1106893
def get_cookies(url, cookiesfile):

    def chrome_decrypt(encrypted_value, key=None, iv=None):
        dec = AES.new(key, AES.MODE_CBC, IV=iv).decrypt(encrypted_value[3:])
        decrypted = dec[:-dec[-1]].decode('utf8')
        return decrypted

    cookies = []
    if sys.platform == 'win32':
        import win32crypt
        conn = sqlite3.connect(cookiesfile)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT name, value, encrypted_value FROM cookies WHERE host_key == "' + url + '"')
        for name, value, encrypted_value in cursor.fetchall():
            if value or (encrypted_value[:3] == b'v10'):
                cookies.append((name, value))
            else:
                decrypted_value = win32crypt.CryptUnprotectData(
                    encrypted_value, None, None, None, 0)[1].decode('utf-8') or 'ERROR'
                cookies.append((name, decrypted_value))

    elif sys.platform == 'linux' or sys.platform == 'darwin':
        my_pass = 'peanuts'.encode('utf8')
        iterations = 1
        salt = b'saltysalt'
        length = 16
        key = PBKDF2(my_pass, salt, length, iterations)
        conn = sqlite3.connect(cookiesfile)
        cursor = conn.cursor()
        iv = b' ' * 16
        select = 'SELECT name, value, encrypted_value FROM cookies WHERE host_key == "' + url + '"'
        select2 = 'SELECT name, value, encrypted_value FROM cookies'
        cursor.execute(select2)
        for name, value, encrypted_value in cursor.fetchall():
            decrypted_tuple = (name, chrome_decrypt(encrypted_value, key=key, iv=iv))
            cookies.append(decrypted_tuple)
    else:
        print('This tool is only supported by linux and Mac')

    conn.close()
    return cookies


if __name__ == '__main__':
    pass


home = expanduser("~")
cookiefile = home + "/Library/Application Support/Google/Chrome/Default/Cookies"
exists = os.path.exists(cookiefile)
print(exists)
cookies = get_cookies('https://www.facebook.com', cookiefile)
print(cookies)
