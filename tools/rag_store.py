import os
import shutil

# 导入 Flashrank (Reranker 始终用轻量级本地版)
from flashrank import Ranker, RerankRequest
# LangChain 组件
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from loguru import logger

# 导入配置
from config import USE_LOCAL_EMBEDDING, EMBEDDING_API_KEY, EMBEDDING_BASE_URL, EMBEDDING_MODEL_NAME


class RAGStore:
    def __init__(self):
        logger.info(f"🚀 [Init] 初始化 RAG 系统 | 模式: {'纯本地' if USE_LOCAL_EMBEDDING else '云端API'}")

        # Embedding
        if USE_LOCAL_EMBEDDING:
            # 【本地模式】加载 HuggingFace 模型 (吃内存，省钱)
            from langchain_huggingface import HuggingFaceEmbeddings
            logger.info(f"📥 正在加载本地模型: {EMBEDDING_MODEL_NAME} (请确保显存/内存充足)...")
            self.embedding = HuggingFaceEmbeddings(
                model_name=EMBEDDING_MODEL_NAME,
                model_kwargs={'device': 'cpu'},
                encode_kwargs={'normalize_embeddings': True} # 输出的向量做归一化，方便后续做相似度搜索
            )
        else:
            # 【云端模式】调用 SiliconFlow API (省内存，极速)
            from langchain_openai import OpenAIEmbeddings
            if not EMBEDDING_API_KEY.startswith("sk-"):
                logger.error("❌ 未配置 EMBEDDING_API_KEY，无法使用云端模式！")
                raise ValueError("API Key Missing")

            logger.info(f"☁️ 正在连接云端 Embedding: {EMBEDDING_MODEL_NAME}...")
            self.embedding = OpenAIEmbeddings(
                model=EMBEDDING_MODEL_NAME,
                openai_api_key=EMBEDDING_API_KEY,
                openai_api_base=EMBEDDING_BASE_URL,
                check_embedding_ctx_length=False # 跳过长度检查，避免报错
            )

        # Reranker:精排序 (Flashrank:为了适应格式，在精排序前后要转换协议)
        # Flashrank 只有 100MB，4G 服务器完全跑得动，为了逻辑简单，保持本地运行
        self.reranker = Ranker(
            model_name="ms-marco-MiniLM-L-12-v2",
            cache_dir="./models"
        )

        # 切分器
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=1200,
            chunk_overlap=250,
            # 明确指明切割方法，按这个顺序依次往后排（如果不指定会默认切）
            separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " "]
        )

        # 向量库
        self.vector_store = Chroma(
            persist_directory="./chroma_db",
            # 选择用该模型来做embedding的工作
            embedding_function=self.embedding
        )
        logger.info("✅ [Init] RAG 系统就绪")

    # RAG - 离线模块(加载与切块/向量化/存入向量数据库)
    def add_documents(self, text_content: str, source_url: str = ""):
        """
        存入向量数据库 (自动分批处理)
        text_content:需要存储的原始文本内容
        source_url:文本的来源标识，用于后续检索时展示出处 (方便AI标识精确来源，比如url)
        """
        if not text_content or len(text_content) < 50:
            logger.warning("⚠️ 内容过短，跳过入库")
            return False

        # 封装 Document(Document是langchain固定接收的对象格式) metadata则指明具体身份
        raw_doc = Document(page_content=text_content, metadata={"source": source_url})
        # 切片
        chunks = self.splitter.split_documents([raw_doc])

        # --- [修复核心] 分批入库 ---
        # 硅基流动限制单次 batch <= 64，我们设为 50 比较安全
        batch_size = 50
        total_chunks = len(chunks)

        for i in range(0, total_chunks, batch_size):
            batch = chunks[i: i + batch_size]
            # 调用向量库内置方法:将这一批次(50个)文本片段发送给 Embedding模型进行向量化，再将生成的向量连同原始文本、元数据一同持久化存储到本地Chroma数据库中
            # 简单讲，此处囊括了 文本向量化+存入向量数据库 两步
            # 注意:在此步前，我们的batch一直都还是非向量形态
            self.vector_store.add_documents(batch)
            logger.info(f"💾 [Store] 分批入库: {len(batch)} 个片段 ({i + len(batch)}/{total_chunks})")

        logger.info(f"✅ [Store] 全部入库完成 (共 {total_chunks} 个片段 | 来源: {source_url})")
        return True

    # RAG - 在线模块(粗排/精排/过滤)
    def query(self, question: str, k_retrieve=50, k_final=6, score_threshold=0.7):
        """
        检索流程: 向量粗排 -> Flashrank 精排
        粗排 - 计算数学距离（长得像就行）；
        精排 - 进行语义对齐（仔细理解出核心逻辑）
        """
        # Phase 1: 粗排
        logger.info(f"🔍 [Search] 向量检索 Top-{k_retrieve}...")
        # 这个doc与后面的Document(xx)指向同一个参数封装，是因为二者(Chroma/langchain-langchain_chroma)已经互相集成好
        docs = self.vector_store.similarity_search(question, k=k_retrieve)

        if not docs:
            logger.warning("⚠️ 未找到相关文档")
            return []

        # Phase 2: 精排
        logger.info(f"⚡️ [Rerank] Flashrank 重排序...")
        # 把数据封装成FlashRank接受的格式(doc.page_content是原始文本内容;doc.metadata是档案来源：比如你可以指定为last_msg.tool_call_id)
        # FlashRank是针对精排序的。所以这里在数据传过去与传回来都需要调整格式。
        passages = []
        for i,doc in enumerate(docs):
            passages.append({"id": str(i), "text": doc.page_content, "meta": doc.metadata})

        # for i, doc in enumerate(docs):
        #     print(doc,'\n')
        #     print(doc.page_content,'\n')
        #     print(doc.metadata,'\n')

        rerank_request = RerankRequest(query=question, passages=passages)
        results = self.reranker.rerank(rerank_request)
        # print(results)

        # Phase 3: 过滤
        final_docs = []
        # 必须得分超过0.6才能返回
        for res in results:
            if res['score'] >= score_threshold:
                # 将FlashRank返回的py字典转化为LangChain接受的Document对象
                doc = Document(page_content=res['text'], metadata=res['meta'])
                # print('doc:::',doc)
                doc.metadata['rerank_score'] = res['score']
                # print('doc2:::',doc)
                final_docs.append(doc)
            if len(final_docs) >= k_final:
                break

        logger.info(f"✅ [Result] 返回 {len(final_docs)} 个高分结果")
        return final_docs

    # RAG检索返回逻辑
    def query_formatted(self,query:str):
        """
        直接返回格式化好的字符串，给Tool和Writer用
        """

        results = self.query(query)

        if not results:
            return "知识库中未找到相关内容。"

        # 格式化返回结果
        formatted_res = []
        for doc in results:
            source = doc.metadata.get('source', 'unknown')
            score = doc.metadata.get('rerank_score', 0)
            formatted_res.append(f"[来源: {source} | 置信度: {score:.2f}]\n{doc.page_content}")
        print('formatted_res:::', formatted_res)

        return "\n\n---\n\n".join(formatted_res)

# --- 测试代码 ---
if __name__ == "__main__":
    # 清理旧库测试
    if os.path.exists("./chroma_db"):
        shutil.rmtree("./chroma_db")

    rag = RAGStore()

    # 模拟入库
    text = "DeepSeek-V3 是一款强大的模型，API 价格非常便宜。SiliconFlow 提供了极速的推理服务。"
    rag.add_documents(text, "test_source")

    # 模拟检索
    res = rag.query("DeepSeek 怎么样？")
    for r in res:
        print('r:::',r)
        print('r.metadata:::',r.metadata)
        print(f"得分: {r.metadata['rerank_score']:.3f} | 内容: {r.page_content}")