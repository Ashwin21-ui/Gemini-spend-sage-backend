import requests

BASE_URL = "http://127.0.0.1:8000"

email = "raghavsengottuvel14@gmail.com"
username = "testuser1234"
password = "Test@1234"


def signup():
    url = f"{BASE_URL}/api/auth/signup"
    payload = {
        "username": username,
        "email": email,
        "password": password
    }

    res = requests.post(url, json=payload)
    print("\n--- SIGNUP ---")
    print(res.status_code, res.json())


def verify_otp(otp_code):
    url = f"{BASE_URL}/api/auth/verify-otp"
    payload = {
        "email": email,
        "otp_code": otp_code,
        "purpose": "signup"
    }

    res = requests.post(url, json=payload)
    print("\n--- VERIFY OTP ---")
    print(res.status_code, res.json())


if __name__ == "__main__":
    signup()

    otp = input("\nEnter OTP received: ").strip()
    verify_otp(otp)