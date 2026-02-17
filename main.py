

# และในส่วน __main__ ตอนท้ายไฟล์:
if __name__ == "__main__":
    try:
        # เริ่ม web server
        run_server()  # ใช้ function จาก server.py แทน keep_alive()
        print("🚀 กำลังเริ่มต้นบอท...")
        
        token = os.getenv("TOKEN")
        if not token:
            print("❌ ไม่พบ TOKEN ใน environment variables")
            exit(1)
        
        print("⏳ รอ 30 วินาทีก่อนเริ่มบอท...")
        time.sleep(30)
        
        bot.run(token)
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดร้ายแรง: {e}")
        traceback.print_exc()

