import smtplib
from email.message import EmailMessage

# --- CONFIGURATION ---
# Use the exact values from the account you are currently logged into
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
# Based on your Google Security settings, this must be:
SMTP_USER = "spendsage77@gmail.com" 
# Use the 16-character App Password you generated (no spaces)
SMTP_PASSWORD = "rokjvjtlmzmilkpc" 
# ---------------------

msg = EmailMessage()
msg.set_content("This is a test email to verify SMTP settings.")
msg['Subject'] = "SMTP Connection Test"
msg['From'] = f"Spend Sage <{SMTP_USER}>"
msg['To'] = SMTP_USER  # Sending it to yourself for the test

try:
    print(f"Connecting to {SMTP_SERVER}...")
    # Create connection
    server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    server.starttls()  # Upgrade to secure connection
    
    print(f"Attempting login for {SMTP_USER}...")
    server.login(SMTP_USER, SMTP_PASSWORD)
    
    print("Login successful! Sending test email...")
    server.send_message(msg)
    
    print("Email sent successfully!")
    server.quit()

except Exception as e:
    print(f"\nConnection Failed!")
    print(f"Error details: {e}")