import requests
import json
import uuid  # 用于生成唯一的submit_id

# 定义请求的URL
generate_video_url = 'https://jimeng.jianying.com/mweb/v1/generate_video?aid=513695&msToken=iUiN1eJL_V2QMUbboCBfQED7Z1XQnP804XRQrF1MdtYR0YrsjkpTtsXPaKQttHlqFQYNWKOXMcICm0jXFYwCXClyrpNb0U_OrIqcjfEpGj6FzvGfvTPU6AKknMvyBEM%3D&a_bogus=YJlYvc2CMsm15xB0A7kz9bdO68D0YW-DgZENagBXOzLY'
mget_generate_task_url = 'https://jimeng.jianying.com/mweb/v1/mget_generate_task?aid=513695'

# 定义请求头
headers = {
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'zh-CN,zh;q=0.9',
    'app-sdk-version': '48.0.0',
    'appid': '513695',
    'appvr': '5.8.0',
    'content-type': 'application/json',
    'cookie': '_tea_web_id=7454781890667644442; x-web-secsdk-uid=68dece4e-cd3d-425a-9c51-c9dac4d3b662; s_v_web_id=verify_m5dbywvv_ikAtz5FH_beT0_4R8y_BjWI_DGj3XoYfLxzN; fpk1=edc2bd9493f9fb557d1cb1f74ad487cddce8cd250f58bb7c3c71adc29c897955a280ec8019ff4b9cd295540668acb797; passport_csrf_token=91b1988dac2458bd66401c665a3e54f9; passport_csrf_token_default=91b1988dac2458bd66401c665a3e54f9; n_mh=qYda4-0WJvO1DEPc-KFvRHGbPI8IGJvmKre0HqTGIeA; is_staff_user=false; store-region=cn-gd; store-region-src=uid; user_spaces_idc={"7425841864957641791":"lf"}; _v2_spipe_web_id=7454782441916629042; passport_mfa_token=CjHx1zoi4cjVO2DqCvHcfjQpEmtHn689UZhZYB9G2u3BmHngn2cGNXgVR1OrMiM8fCibGkoKPD8q3cEtMXEc2FAoDbLD4I2epM79pqFdkVvdch6h7GI9VaH3M7k1gtmvKL2aqrL9byIJXfNfeRVkCt8CABDz0OUNGPax0WwgAiIBAwep5kI%3D; d_ticket=c0e886bbaa50eac37b6e86145136c1be1976a; sid_guard=d6d4fdff2177e233f3f11dd540f017ee%7C1735704008%7C5184000%7CSun%2C+02-Mar-2025+04%3A00%3A08+GMT; uid_tt=48632d670824a633253aab0b7da239c1; uid_tt_ss=48632d670824a633253aab0b7da239c1; sid_tt=d6d4fdff2177e233f3f11dd540f017ee; sessionid=d6d4fdff2177e233f3f11dd540f017ee; sessionid_ss=d6d4fdff2177e233f3f11dd540f017ee; sid_ucp_v1=1.0.0-KDBjYTVkZjVkOTYyZGEwOGJiMDIzNDRmYWY1YWY0MTk5MTExM2VjNmMKHwjku6DB4MydBhDI-9K7BhifrR8gDDCfhoKzBjgIQCYaAmxmIiBkNmQ0ZmRmZjIxNzdlMjMzZjNmMTFkZDU0MGYwMTdlZQ; ssid_ucp_v1=1.0.0-KDBjYTVkZjVkOTYyZGEwOGJiMDIzNDRmYWY1YWY0MTk5MTExM2VjNmMKHwjku6DB4MydBhDI-9K7BhifrR8gDDCfhoKzBjgIQCYaAmxmIiBkNmQ0ZmRmZjIxNzdlMjMzZjNmMTFkZDU0MGYwMTdlZQ; dm_auid=ioTXiEKvMywaGwO5AUZI2Um9cpJLauDlwCjmWnvpr1o=; uifid_temp=ba692b693ca3eb3b3b98eb2dd3f293d28115d3b4890a3c18bfbf2ef29d023e5285638f67aef0b082c029f1b22774ce88197768fd52bc41640496935dcf81feaa0f4973bd865546a0dbf76c4a3028ce1c971b9951dc69bb54c29e99c8a7d312bfa9a9707d0f928e36fe13ed18d1bcad17; uifid=ba692b693ca3eb3b3b98eb2dd3f293d28115d3b4890a3c18bfbf2ef29d023e5285638f67aef0b082c029f1b22774ce884e0b8b5fd7b8f4d52e0554abc93292ac55b62dc0c87c3462beaba97872d204139c4bafc145dca026d9be7b40eac2e8abbd552d79b8dff4962855ea248e7412117c08d2f04b71288a6c33860df2ba30b0b52656a63ee98c581e559cadbbc2dc7cc54d25dbba73a8127d09d856084ee6bc277388a07e78d8524851469e75199217d2301dc1ec66298495cc38890dd2e15bb07d6281ad37dcb11519a608fe823725; ttwid=1|EA-LFYJA6Io3U114OtRgPtkjyOebntgpgXVbKI6Dc6A|1735805891|b4e13e1db46c4848e345c2e32d6381cef770c3c5eeb86b18250c18bac0db796b; odin_tt=2c2fb6a9a842d3f5ab61c1238873fc0560e0c05a7b02420e99bd96708a6d953273c88b7eae3981bfc7643862897116b2ed4b378590810eb84a1ac88f9f8a2979',
    'device-time': '1735805955',
    'lan': 'zh-Hans',
    'loc': 'cn',
    'origin': 'https://jimeng.jianying.com',
    'pf': '7',
    'priority': 'u=1, i',
    'referer': 'https://jimeng.jianying.com/ai-tool/video/generate',
    'sec-ch-ua': '"Google Chrome";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'sign': 'af98fdb6812e301b600022f00968561f',
    'sign-ver': '1',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36'
}

# 动态生成submit_id
submit_id = str(uuid.uuid4())

# 定义请求体
generate_video_payload = {
    "submit_id": submit_id,  # 使用动态生成的submit_id
    "task_extra": "{\"promptSource\":\"custom\",\"originSubmitId\":\"0340110f-5a94-42a9-b737-f4518f90361f\",\"isDefaultSeed\":1,\"originTemplateId\":\"\",\"imageNameMapping\":{},\"isUseAiGenPrompt\":false,\"batchNumber\":1}",
    "http_common_info": {"aid": 513695},
    "input": {
        "video_aspect_ratio": "16:9",
        "seed": 2934141961,
        "video_gen_inputs": [
            {
                "prompt": "现代美少女在海边",
                "fps": 24,
                "duration_ms": 5000,
                "video_mode": 2,
                "template_id": ""
            }
        ],
        "priority": 0,
        "model_req_key": "dreamina_ic_generate_video_model_vgfm_lite"
    },
    "mode": "workbench",
    "history_option": {},
    "commerce_info": {
        "resource_id": "generate_video",
        "resource_id_type": "str",
        "resource_sub_type": "aigc",
        "benefit_type": "basic_video_operation_vgfm_lite"
    },
    "client_trace_data": {}
}

# 发送生成视频的请求
print("正在生成视频...")
response_generate_video = requests.post(generate_video_url, headers=headers, json=generate_video_payload)

# 检查生成视频请求是否成功
if response_generate_video.status_code == 200:
    task_id = response_generate_video.json()["data"]["aigc_data"]["task"]["task_id"]
    print(f"视频生成任务已创建，task_id: {task_id}")
else:
    print(f"视频生成请求失败，状态码: {response_generate_video.status_code}")
    exit()

# 等待视频生成完成（这里可以根据实际情况调整等待时间）
import time
print("等待视频生成完成...")
time.sleep(30)  # 假设视频生成需要30秒

# 发送获取生成任务的请求
print("正在查询视频生成状态...")
mget_generate_task_payload = {"task_id_list": [task_id]}
response_mget_generate_task = requests.post(mget_generate_task_url, headers=headers, json=mget_generate_task_payload)

# 检查查询请求是否成功
if response_mget_generate_task.status_code == 200:
    task_status = response_mget_generate_task.json()["data"]["task_map"][task_id]["status"]
    if task_status == 50:  # 假设50表示视频生成完成
        video_url = response_mget_generate_task.json()["data"]["task_map"][task_id]["item_list"][0]["video"]["transcoded_video"]["origin"]["video_url"]
        print(f"视频生成完成，视频URL: {video_url}")

        # 下载视频
        print("正在下载视频...")
        video_response = requests.get(video_url, headers=headers)
        if video_response.status_code == 200:
            with open("generated_video.mp4", "wb") as f:
                f.write(video_response.content)
            print("视频已保存为 generated_video.mp4")
        else:
            print(f"视频下载失败，状态码: {video_response.status_code}")
    else:
        print(f"视频生成未完成，当前状态: {task_status}")
else:
    print(f"查询视频生成状态失败，状态码: {response_mget_generate_task.status_code}")
