# --------------------------------------------------------------------------------------------------
# ฟังก์ชันเช็คเลเวลผู้ใช้
async def check_user_level(interaction: discord.Interaction):
    """แสดงเลเวลและ EXP ของผู้ใช้"""
    try:
        user_id = str(interaction.user.id)
        
        if user_id not in user_data:
            # ถ้ายังไม่มีข้อมูล ให้สร้างข้อมูลใหม่
            user_data[user_id] = {"exp": 0, "level": 0}
            save_user_data()
        
        user_exp = user_data[user_id]["exp"]
        user_level = user_data[user_id]["level"]
        
        # คำนวณ EXP ที่ต้องการสำหรับเลเวลถัดไป
        next_level_exp = 0
        next_level_role_name = "ไม่มี"
        if user_level < 4:
            next_level = user_level + 1
            next_level_exp = LEVELS[next_level]["exp"]
            next_level_role_name = LEVELS[next_level]["role_name"]  # เปลี่ยนเป็น role_name
            exp_needed = next_level_exp - user_exp
        else:
            exp_needed = 0
            next_level_role_name = "สูงสุดแล้ว"
        
        # กำหนด role_name ปัจจุบัน
        current_role_name = "Level 0"
        if user_level > 0 and user_level in LEVELS:
            current_role_name = LEVELS[user_level]["role_name"]  # เปลี่ยนเป็น role_name
        
        embed = discord.Embed(
            title=f"🍣 ระดับของคุณ {interaction.user.display_name}",
            color=0x00FF99
        )
        embed.add_field(name="🎮 ระดับปัจจุบัน", value=f"**{current_role_name}**", inline=True)  # แสดงชื่อระดับ
        embed.add_field(name="⭐ EXP สะสม", value=f"**{user_exp:,} EXP**", inline=True)
        
        if user_level < 4:
            embed.add_field(
                name="🎯 ระดับถัดไป", 
                value=f"ต้องการอีก **{exp_needed:,} EXP** เพื่อยศ **{next_level_role_name}**",  # แสดงชื่อระดับ
                inline=False
            )
        else:
            embed.add_field(
                name="🏆 สูงสุดแล้ว!", 
                value="คุณถึงระดับสูงสุดแล้ว! 🎉", 
                inline=False
            )
        
        # แสดงความคืบหน้า
        if user_level < 4:
            current_level_exp = LEVELS[user_level]["exp"] if user_level > 0 else 0
            progress = user_exp - current_level_exp
            total_for_level = next_level_exp - current_level_exp
            percentage = (progress / total_for_level) * 100 if total_for_level > 0 else 0
            
            progress_bar = "🟢" * int(percentage / 20) + "⚫" * (5 - int(percentage / 20))
            embed.add_field(
                name="🌱 ความคืบหน้า",
                value=f"{progress_bar} {percentage:.1f}%",
                inline=False
            )
        
        embed.set_footer(text="ได้รับ EXP จากการซื้อสินค้าในร้าน")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการเช็คเลเวล: {e}")
        await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการเช็คเลเวล", ephemeral=True)

# --------------------------------------------------------------------------------------------------
async def check_user_level_as_command(ctx, member):
    """แสดงเลเวลและ EXP ของผู้ใช้ (สำหรับคำสั่ง)"""
    try:
        user_id = str(member.id)
        
        if user_id not in user_data:
            # ถ้ายังไม่มีข้อมูล ให้สร้างข้อมูลใหม่
            user_data[user_id] = {"exp": 0, "level": 0}
            save_user_data()
        
        user_exp = user_data[user_id]["exp"]
        user_level = user_data[user_id]["level"]
        
        # คำนวณ EXP ที่ต้องการสำหรับเลเวลถัดไป
        next_level_exp = 0
        next_level_role_name = "ไม่มี"
        if user_level < 4:
            next_level = user_level + 1
            next_level_exp = LEVELS[next_level]["exp"]
            next_level_role_name = LEVELS[next_level]["role_name"]  # เปลี่ยนเป็น role_name
            exp_needed = next_level_exp - user_exp
        else:
            exp_needed = 0
            next_level_role_name = "สูงสุดแล้ว"
        
        # กำหนด role_name ปัจจุบัน
        current_role_name = "Level 0"
        if user_level > 0 and user_level in LEVELS:
            current_role_name = LEVELS[user_level]["role_name"]  # เปลี่ยนเป็น role_name
        
        embed = discord.Embed(
            title=f"🍣 ระดับของคุณ {member.display_name}",
            color=0x00FF99
        )
        embed.add_field(name="🎮 ระดับปัจจุบัน", value=f"**{current_role_name}**", inline=True)  # แสดงชื่อระดับ
        embed.add_field(name="⭐ EXP สะสม", value=f"**{user_exp:,} EXP**", inline=True)
        
        if user_level < 4:
            embed.add_field(
                name="🎯 ระดับถัดไป", 
                value=f"ต้องการอีก **{exp_needed:,} EXP** เพื่อยศ **{next_level_role_name}**",  # แสดงชื่อระดับ
                inline=False
            )
        else:
            embed.add_field(
                name="🏆 สูงสุดแล้ว!", 
                value="คุณถึงระดับสูงสุดแล้ว! 🎉", 
                inline=False
            )
        
        # แสดงความคืบหน้า
        if user_level < 4:
            current_level_exp = LEVELS[user_level]["exp"] if user_level > 0 else 0
            progress = user_exp - current_level_exp
            total_for_level = next_level_exp - current_level_exp
            percentage = (progress / total_for_level) * 100 if total_for_level > 0 else 0
            
            progress_bar = "🟢" * int(percentage / 20) + "⚫" * (5 - int(percentage / 20))
            embed.add_field(
                name="🌱 ความคืบหน้า",
                value=f"{progress_bar} {percentage:.1f}%",
                inline=False
            )
        
        embed.set_footer(text="ได้รับ EXP จากการซื้อสินค้าในร้าน")
        await ctx.send(embed=embed)
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการเช็คเลเวล: {e}")
        await ctx.send("❌ เกิดข้อผิดพลาดในการเช็คเลเวล")
