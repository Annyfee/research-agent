"""
硅基流动 (SiliconFlow) Embedding API 测试脚本
"""
import requests
import json
from config import EMBEDDING_API_KEY

# ==================== 配置 ====================
SILICONFLOW_API_KEY = EMBEDDING_API_KEY  # ← 填入你的 Key
SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"

# ==================== 测试函数 ====================
def test_siliconflow_embedding():
    """测试硅基流动 Embedding API"""

    print("="*60)
    print("硅基流动 Embedding API 测试")
    print("="*60)

    # 测试文本
    test_text = "DeepSeek-V3 是一个强大的语言模型"

    print(f"\n测试文本: {test_text}\n")

    # API 调用
    url = f"{SILICONFLOW_BASE_URL}/embeddings"
    headers = {
        "Authorization": f"Bearer {SILICONFLOW_API_KEY}",
        "Content-Type": "application/json"
    }

    # 测试三个模型
    models_to_test = [
        "BAAI/bge-large-zh-v1.5",  # 中文优化
        "BAAI/bge-m3",             # 多语言
        "text-embedding-ada-002"   # OpenAI 兼容
    ]

    for model in models_to_test:
        print(f">>> 测试模型: {model}")

        payload = {
            "model": model,
            "input": test_text
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)

            print(f"    状态码: {response.status_code}")

            if response.status_code == 200:
                data = response.json()

                if "data" in data and len(data["data"]) > 0:
                    embedding = data["data"][0]["embedding"]
                    usage = data.get("usage", {})

                    print(f"    ✅ 成功！")
                    print(f"    向量维度: {len(embedding)}")
                    print(f"    前 5 个值: {embedding[:5]}")
                    print(f"    消耗 tokens: {usage.get('total_tokens', 'N/A')}")
                    print()
                else:
                    print(f"    ❌ 响应格式异常")
                    print(f"    {json.dumps(data, ensure_ascii=False)}")
                    print()
            else:
                print(f"    ❌ 请求失败")
                try:
                    error = response.json()
                    print(f"    错误信息: {json.dumps(error, ensure_ascii=False)}")
                except:
                    print(f"    错误信息: {response.text}")
                print()

        except Exception as e:
            print(f"    ❌ 异常: {str(e)}\n")

    print("="*60)


def test_with_langchain():
    """测试 LangChain 集成"""
    print("\n" + "="*60)
    print("LangChain 集成测试")
    print("="*60 + "\n")

    try:
        from langchain_openai import OpenAIEmbeddings

        # 使用硅基流动的 API
        embeddings = OpenAIEmbeddings(
            model="BAAI/bge-large-zh-v1.5",
            openai_api_key=SILICONFLOW_API_KEY,
            openai_api_base=SILICONFLOW_BASE_URL
        )

        # 测试 embed_query
        print(">>> 测试 embed_query()")
        query_result = embeddings.embed_query("测试文本")
        print(f"✅ 查询向量维度: {len(query_result)}")
        print(f"前 5 个值: {query_result[:5]}\n")

        # 测试 embed_documents
        print(">>> 测试 embed_documents()")
        docs = ["文档1", "文档2", "文档3"]
        docs_result = embeddings.embed_documents(docs)
        print(f"✅ 文档数量: {len(docs_result)}")
        print(f"每个向量维度: {len(docs_result[0])}\n")

        print("="*60)
        print("✅ LangChain 集成测试通过！")
        print("="*60)

    except ImportError:
        print("⚠️ 未安装 langchain-openai，跳过集成测试")
        print("安装命令: pip install langchain-openai")
    except Exception as e:
        print(f"❌ 集成测试失败: {str(e)}")


if __name__ == "__main__":
    # 检查配置
    if SILICONFLOW_API_KEY == "sk-your-siliconflow-key":
        print("⚠️ 请先配置 SILICONFLOW_API_KEY")
        print("在第 7 行修改")
        exit(1)

    # 运行测试
    test_siliconflow_embedding()

    # LangChain 集成测试
    test_with_langchain()

    print("\n✅ 所有测试完成")