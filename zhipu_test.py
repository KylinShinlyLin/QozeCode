from zai import ZhipuAiClient

if __name__ == '__main__':
    # 初始化客户端
    client = ZhipuAiClient(
        base_url="https://open.bigmodel.cn/api/paas/v4",
        api_key="634c213391894826bc02bb67d264353f.BhmmgT4rT4kepIwb")

    # 创建聊天完成请求
    response = client.chat.completions.create(
        model="glm-4.7",
        messages=[
            {
                "role": "system",
                "content": "你是一个有用的AI助手。"
            },
            {
                "role": "user",
                "content": "你好，请介绍一下自己。"
            }
        ],
        stream=True,
        temperature=0.6
    )

    # 获取回复
    for message_chunk in response:
        print(message_chunk)
