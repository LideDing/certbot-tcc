"""
certbot-tcc：基于腾讯云 DNSPod API 3.0 的 Certbot DNS-01 认证插件。

工作原理：
  Let's Encrypt 在颁发证书前，需要验证你对域名的控制权。
  DNS-01 验证方式要求在域名的 DNS 中添加一条特定的 TXT 记录。
  本插件通过腾讯云 DNSPod API 自动完成该 TXT 记录的创建和清理，
  从而实现无需人工干预的自动化证书申请（包括通配符证书）。

凭证加载优先级（由高到低）：
  1. 环境变量：TENCENTCLOUD_SECRET_ID / TENCENTCLOUD_SECRET_KEY
  2. --certbot-tcc-credentials 指定的 INI 文件
  3. 默认凭证文件：~/.tcc.ini

使用方式（环境变量）：
  export TENCENTCLOUD_SECRET_ID=AKIDxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
  export TENCENTCLOUD_SECRET_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
  certbot certonly \
    --authenticator certbot-tcc \
    -d example.com -d '*.example.com'

使用方式（凭证文件）：
  certbot certonly \
    --authenticator certbot-tcc \
    --certbot-tcc-credentials /path/to/tcc.ini \
    -d example.com -d '*.example.com'

凭证文件（tcc.ini）格式：
  certbot_tcc_secret_id  = AKIDxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
  certbot_tcc_secret_key = xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
"""

import logging
import os
from collections import namedtuple
from typing import Any, Callable, List, Optional, Tuple

import zope.interface
from certbot import errors, interfaces
from certbot.plugins import dns_common

from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.dnspod.v20210323 import dnspod_client, models

logger = logging.getLogger(__name__)

# 用于承载从 DNSPod 查询到的域名信息
DomainInfo = namedtuple("DomainInfo", ["id", "name"])

# 环境变量名
_ENV_SECRET_ID  = "TENCENTCLOUD_SECRET_ID"
_ENV_SECRET_KEY = "TENCENTCLOUD_SECRET_KEY"

# 默认凭证文件路径
_DEFAULT_CREDENTIALS_PATH = os.path.expanduser("~/.tcc.ini")


def _load_credentials_from_env() -> Optional[Tuple[str, str]]:
    """
    尝试从环境变量中读取凭证。

    :returns: (secret_id, secret_key) 或 None（环境变量未设置时）
    """
    secret_id  = os.environ.get(_ENV_SECRET_ID)
    secret_key = os.environ.get(_ENV_SECRET_KEY)
    if secret_id and secret_key:
        logger.debug("从环境变量 %s / %s 加载凭证", _ENV_SECRET_ID, _ENV_SECRET_KEY)
        return secret_id, secret_key
    return None


@zope.interface.implementer(interfaces.IAuthenticator)
@zope.interface.provider(interfaces.IPluginFactory)
class Authenticator(dns_common.DNSAuthenticator):
    """
    Certbot DNS-01 认证插件：certbot-tcc

    通过腾讯云 DNSPod API 3.0 自动管理 DNS TXT 记录，以完成 Let's Encrypt 的 DNS-01 挑战。
    支持普通域名和通配符域名（*.example.com）。
    """

    # 在 certbot --help 中显示的插件描述
    description = "使用腾讯云 DNSPod API 3.0 自动完成 DNS-01 验证，申请 Let's Encrypt 证书"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # credentials 将在 _setup_credentials 中被赋值
        self.credentials: Optional[dns_common.CredentialsConfiguration] = None

    @classmethod
    def add_parser_arguments(
        cls, add: Callable[..., None], default_propagation_seconds: int = 10
    ) -> None:
        """
        向 certbot 命令行注册本插件专属参数。

        --certbot-tcc-credentials：指定凭证文件路径（可选，有环境变量时可省略）
        --certbot-tcc-propagation-seconds：等待 DNS 记录生效的秒数（默认 10 秒）
        """
        super().add_parser_arguments(add, default_propagation_seconds)
        add(
            "credentials",
            help=(
                "腾讯云 API 凭证 INI 文件路径，需包含 secret_id 和 secret_key。"
                f"可省略：优先读取环境变量 {_ENV_SECRET_ID}/{_ENV_SECRET_KEY}，"
                f"其次尝试默认路径 {_DEFAULT_CREDENTIALS_PATH}。"
            ),
            default=None,
        )

    def more_info(self) -> str:
        """返回插件的详细说明，用于 certbot --help 输出。"""
        return (
            "本插件通过腾讯云 DNSPod API 3.0 自动创建/删除 DNS TXT 记录，"
            "以完成 Let's Encrypt DNS-01 域名验证挑战。"
            f"凭证优先级：环境变量 > --certbot-tcc-credentials 文件 > {_DEFAULT_CREDENTIALS_PATH}。"
        )

    def _setup_credentials(self) -> None:
        """
        加载凭证，按以下优先级依次尝试：
          1. 环境变量 TENCENTCLOUD_SECRET_ID / TENCENTCLOUD_SECRET_KEY
          2. --certbot-tcc-credentials 指定的 INI 文件
          3. 默认凭证文件 ~/.tcc.ini
        """
        # 优先级 1：环境变量
        if _load_credentials_from_env():
            logger.debug("将使用环境变量中的凭证，跳过凭证文件加载。")
            return

        # 优先级 2：命令行指定的凭证文件
        # 优先级 3：默认路径（conf 值为 None 时回退到默认路径）
        credentials_path = self.conf("credentials") or _DEFAULT_CREDENTIALS_PATH

        if not os.path.exists(credentials_path):
            raise errors.PluginError(
                f"未找到凭证文件 '{credentials_path}'。"
                f"请通过以下任一方式提供凭证：\n"
                f"  1. 设置环境变量 {_ENV_SECRET_ID} / {_ENV_SECRET_KEY}\n"
                f"  2. 使用 --certbot-tcc-credentials 指定 INI 文件\n"
                f"  3. 将凭证文件放置于默认路径 {_DEFAULT_CREDENTIALS_PATH}"
            )

        # 动态覆盖 conf 值，让 _configure_credentials 读取正确的文件路径
        self.config.certbot_tcc_credentials = credentials_path  # type: ignore[attr-defined]
        self.credentials = self._configure_credentials(
            "credentials",
            "腾讯云 API 凭证文件",
            {
                "secret_id": "腾讯云 SecretId（以 AKID 开头）",
                "secret_key": "腾讯云 SecretKey",
            },
        )

    def _perform(self, domain: str, validation_name: str, validation: str) -> None:
        """
        DNS-01 挑战执行阶段：创建 TXT 记录。

        certbot 框架在发起验证前调用此方法。
        :param domain: 申请证书的主域名，如 example.com
        :param validation_name: TXT 记录的完整名称，如 _acme-challenge.example.com
        :param validation: TXT 记录的值（由 Let's Encrypt 指定的随机字符串）
        """
        self._get_tcc_client().add_txt_record(domain, validation_name, validation)

    def _cleanup(self, domain: str, validation_name: str, validation: str) -> None:
        """
        DNS-01 挑战清理阶段：删除 TXT 记录。

        certbot 框架在验证完成（无论成功或失败）后调用此方法，清理临时 TXT 记录。
        :param domain: 申请证书的主域名
        :param validation_name: TXT 记录的完整名称
        :param validation: TXT 记录的值
        """
        self._get_tcc_client().del_txt_record(domain, validation_name, validation)

    def _get_tcc_client(self) -> "_TCCClient":
        """
        按优先级解析凭证并创建 DNSPod API 客户端实例：
          1. 环境变量
          2. 凭证文件（已在 _setup_credentials 中加载到 self.credentials）
        """
        # 优先级 1：环境变量
        env_cred = _load_credentials_from_env()
        if env_cred:
            return _TCCClient(secret_id=env_cred[0], secret_key=env_cred[1])

        # 优先级 2/3：凭证文件
        assert self.credentials is not None, "_setup_credentials 未被调用"
        return _TCCClient(
            secret_id=self.credentials.conf("secret_id"),
            secret_key=self.credentials.conf("secret_key"),
        )


class _TCCClient:
    """
    腾讯云 DNSPod API 3.0 客户端封装。

    负责与 DNSPod API 通信，提供：
      - 查找域名信息
      - 添加 TXT 记录
      - 删除 TXT 记录
    """

    def __init__(self, secret_id: str, secret_key: str) -> None:
        """
        初始化腾讯云 SDK 客户端。

        腾讯云 API 3.0 使用签名 V3（TC3-HMAC-SHA256）认证，
        SDK 会自动处理签名，只需传入 SecretId 和 SecretKey 即可。

        :param secret_id: 腾讯云 SecretId（以 AKID 开头）
        :param secret_key: 腾讯云 SecretKey
        """
        cred = credential.Credential(secret_id, secret_key)
        # DNSPod API 无需指定地域，传空字符串即可
        self.client = dnspod_client.DnspodClient(cred, "")

    # -------------------------------------------------------------------------
    # 公开方法
    # -------------------------------------------------------------------------

    def add_txt_record(
        self, domain_name: str, record_name: str, record_content: str
    ) -> None:
        """
        为指定域名添加一条 TXT 记录。

        流程：
          1. 根据 domain_name 从 DNSPod 查找对应的主域名及其 ID
          2. 计算子域名部分（record_name 去掉主域名后缀）
          3. 调用 CreateRecord 接口创建 TXT 记录

        :param domain_name: 申请证书的主域名，如 example.com 或 sub.example.com
        :param record_name: TXT 记录完整名称，如 _acme-challenge.example.com
        :param record_content: TXT 记录内容（验证值）
        :raises errors.PluginError: API 调用失败时抛出
        """
        domain_info = self._find_domain_info(domain_name)
        sub_domain = self._get_sub_domain(record_name, domain_info)

        logger.debug(
            "添加 TXT 记录：%s.%s = %s", sub_domain, domain_info.name, record_content
        )

        req = models.CreateRecordRequest()
        req.Domain = domain_info.name
        req.DomainId = domain_info.id
        req.SubDomain = sub_domain
        req.RecordType = "TXT"
        req.RecordLine = "默认"   # 使用默认线路，适用于所有运营商
        req.Value = record_content
        req.TTL = 60              # 设置较短 TTL，加快 DNS 生效速度

        try:
            resp = self.client.CreateRecord(req)
            logger.debug("TXT 记录创建成功，RecordId: %s", resp.RecordId)
        except TencentCloudSDKException as e:
            raise errors.PluginError(
                f"创建 TXT 记录失败（{sub_domain}.{domain_info.name}）：{e}"
            ) from e

    def del_txt_record(
        self, domain_name: str, record_name: str, record_content: str
    ) -> None:
        """
        删除指定域名下匹配的 TXT 记录。

        通过 record_name 和 record_content 同时匹配，避免误删其他同名记录
        （例如同时申请多个域名证书时可能产生多条 _acme-challenge TXT 记录）。

        :param domain_name: 申请证书的主域名
        :param record_name: TXT 记录完整名称
        :param record_content: TXT 记录内容（用于精确匹配）
        :raises errors.PluginError: 查找域名失败时抛出；删除单条记录失败仅记录警告
        """
        domain_info = self._find_domain_info(domain_name)
        sub_domain = self._get_sub_domain(record_name, domain_info)
        record_ids = self._find_txt_record_ids(domain_info, sub_domain, record_content)

        if not record_ids:
            logger.debug("未找到需要删除的 TXT 记录：%s", record_name)
            return

        for record_id in record_ids:
            logger.debug("删除 TXT 记录，RecordId: %s", record_id)
            req = models.DeleteRecordRequest()
            req.Domain = domain_info.name
            req.DomainId = domain_info.id
            req.RecordId = record_id
            try:
                self.client.DeleteRecord(req)
            except TencentCloudSDKException as e:
                # 删除失败不阻断主流程，仅记录警告
                logger.warning(
                    "删除 TXT 记录失败（RecordId: %s）：%s", record_id, e
                )

    # -------------------------------------------------------------------------
    # 私有辅助方法
    # -------------------------------------------------------------------------

    def _get_sub_domain(self, record_name: str, domain_info: DomainInfo) -> str:
        """
        从完整记录名中提取子域名部分。

        示例：
          record_name  = "_acme-challenge.example.com"
          domain_info.name = "example.com"
          返回值       = "_acme-challenge"

          record_name  = "_acme-challenge.sub.example.com"
          domain_info.name = "example.com"
          返回值       = "_acme-challenge.sub"
        """
        # record_name 末尾是 ".<主域名>"，截掉该部分即为子域名
        return record_name[: -(len(domain_info.name) + 1)]

    def _find_domain_info(self, domain_name: str) -> DomainInfo:
        """
        在 DNSPod 账号下查找与 domain_name 匹配的主域名信息。

        支持多级子域名：对于 sub.example.com，会找到主域名 example.com。
        分页获取所有域名（每页最多 3000 条）。

        :param domain_name: 需要查找的域名（可以是子域名）
        :returns: DomainInfo(id, name)
        :raises errors.PluginError: 未找到匹配域名或 API 调用失败时抛出
        """
        req = models.DescribeDomainListRequest()
        req.Limit = 3000  # 单次最多拉取 3000 条

        try:
            resp = self.client.DescribeDomainList(req)
        except TencentCloudSDKException as e:
            raise errors.PluginError(f"获取域名列表失败：{e}") from e

        # 遍历所有域名，寻找最长后缀匹配（避免 a.com 错误匹配 ba.com）
        best: Optional[DomainInfo] = None
        for d in resp.DomainList:
            if domain_name == d.Name or domain_name.endswith("." + d.Name):
                if best is None or len(d.Name) > len(best.name):
                    best = DomainInfo(d.DomainId, d.Name)

        if best is None:
            raise errors.PluginError(
                f"在 DNSPod 账号下未找到域名 '{domain_name}' 对应的主域名，"
                f"请确认该域名已添加到 DNSPod 并且 API 密钥有访问权限。"
            )

        logger.debug("找到主域名：%s（ID: %s）", best.name, best.id)
        return best

    def _find_txt_record_ids(
        self, domain_info: DomainInfo, sub_domain: str, record_content: str
    ) -> List[int]:
        """
        查找指定子域名下值匹配的 TXT 记录 ID 列表。

        通过 record_content 精确匹配，只删除本次申请创建的记录。

        :param domain_info: 主域名信息
        :param sub_domain: 子域名，如 _acme-challenge
        :param record_content: TXT 记录值，用于精确匹配
        :returns: 匹配的 RecordId 列表（通常只有一条）
        """
        req = models.DescribeRecordListRequest()
        req.Domain = domain_info.name
        req.DomainId = domain_info.id
        req.Subdomain = sub_domain
        req.RecordType = "TXT"
        req.ErrorOnEmpty = "no"  # 记录为空时不报错，返回空列表

        try:
            resp = self.client.DescribeRecordList(req)
        except TencentCloudSDKException as e:
            logger.warning("查询 TXT 记录列表失败：%s", e)
            return []

        if not resp.RecordList:
            return []

        # 按 record_content 精确匹配，避免误删其他 TXT 记录
        matched_ids = [
            r.RecordId
            for r in resp.RecordList
            if r.Value == record_content
        ]
        logger.debug(
            "在 %s.%s 下找到 %d 条匹配的 TXT 记录",
            sub_domain, domain_info.name, len(matched_ids),
        )
        return matched_ids
