"""
certbot_tcc 单元测试

使用 unittest.mock 模拟腾讯云 SDK，无需真实 API 密钥即可运行测试。

运行方式：
    pip install pytest
    pytest tests/ -v
"""

import unittest
from unittest.mock import MagicMock, patch, PropertyMock

from certbot import errors

from certbot_tcc import _TCCClient, DomainInfo


# ---------------------------------------------------------------------------
# 辅助：构造模拟的 DNSPod SDK 响应对象
# ---------------------------------------------------------------------------

def _make_domain(domain_id: int, name: str):
    """构造模拟的域名对象（对应 SDK 的 DomainListItem）"""
    d = MagicMock()
    d.DomainId = domain_id
    d.Name = name
    return d


def _make_record(record_id: int, value: str):
    """构造模拟的记录对象（对应 SDK 的 RecordListItem）"""
    r = MagicMock()
    r.RecordId = record_id
    r.Value = value
    return r


# ---------------------------------------------------------------------------
# _TCCClient 测试
# ---------------------------------------------------------------------------

class TestTCCClient(unittest.TestCase):

    def setUp(self):
        """每个测试用例前，创建一个持有 mock SDK 客户端的 _TCCClient 实例。"""
        # patch DnspodClient，避免实际网络调用
        with patch("certbot_tcc.dnspod_client.DnspodClient") as mock_cls:
            self.mock_sdk = MagicMock()
            mock_cls.return_value = self.mock_sdk
            self.client = _TCCClient("fake_secret_id", "fake_secret_key")
        # 直接替换内部 client，确保后续调用走 mock
        self.client.client = self.mock_sdk

    # --- _find_domain_info ---

    def test_find_domain_info_exact_match(self):
        """精确匹配：domain_name 与 DNSPod 中的域名完全一致。"""
        resp = MagicMock()
        resp.DomainList = [_make_domain(100, "example.com")]
        self.mock_sdk.DescribeDomainList.return_value = resp

        info = self.client._find_domain_info("example.com")

        self.assertEqual(info.id, 100)
        self.assertEqual(info.name, "example.com")

    def test_find_domain_info_subdomain_match(self):
        """子域名匹配：sub.example.com 应匹配主域名 example.com。"""
        resp = MagicMock()
        resp.DomainList = [_make_domain(100, "example.com")]
        self.mock_sdk.DescribeDomainList.return_value = resp

        info = self.client._find_domain_info("sub.example.com")

        self.assertEqual(info.name, "example.com")

    def test_find_domain_info_longest_match(self):
        """最长后缀匹配：sub.example.com 应优先匹配 sub.example.com 而非 example.com。"""
        resp = MagicMock()
        resp.DomainList = [
            _make_domain(100, "example.com"),
            _make_domain(200, "sub.example.com"),
        ]
        self.mock_sdk.DescribeDomainList.return_value = resp

        info = self.client._find_domain_info("sub.example.com")

        self.assertEqual(info.id, 200)
        self.assertEqual(info.name, "sub.example.com")

    def test_find_domain_info_not_found(self):
        """找不到匹配域名时，应抛出 PluginError。"""
        resp = MagicMock()
        resp.DomainList = [_make_domain(100, "other.com")]
        self.mock_sdk.DescribeDomainList.return_value = resp

        with self.assertRaises(errors.PluginError) as ctx:
            self.client._find_domain_info("example.com")
        self.assertIn("未找到域名", str(ctx.exception))

    # --- _get_sub_domain ---

    def test_get_sub_domain_simple(self):
        """简单子域名提取。"""
        info = DomainInfo(1, "example.com")
        result = self.client._get_sub_domain("_acme-challenge.example.com", info)
        self.assertEqual(result, "_acme-challenge")

    def test_get_sub_domain_nested(self):
        """多级子域名提取。"""
        info = DomainInfo(1, "example.com")
        result = self.client._get_sub_domain("_acme-challenge.sub.example.com", info)
        self.assertEqual(result, "_acme-challenge.sub")

    # --- add_txt_record ---

    def test_add_txt_record_success(self):
        """正常添加 TXT 记录。"""
        # 模拟 DescribeDomainList 返回
        domain_resp = MagicMock()
        domain_resp.DomainList = [_make_domain(100, "example.com")]
        self.mock_sdk.DescribeDomainList.return_value = domain_resp

        # 模拟 CreateRecord 返回
        create_resp = MagicMock()
        create_resp.RecordId = 999
        self.mock_sdk.CreateRecord.return_value = create_resp

        self.client.add_txt_record(
            "example.com",
            "_acme-challenge.example.com",
            "validation_token_123",
        )

        # 验证 CreateRecord 被调用，且参数正确
        self.mock_sdk.CreateRecord.assert_called_once()
        req = self.mock_sdk.CreateRecord.call_args[0][0]
        self.assertEqual(req.SubDomain, "_acme-challenge")
        self.assertEqual(req.RecordType, "TXT")
        self.assertEqual(req.Value, "validation_token_123")

    def test_add_txt_record_api_error(self):
        """API 调用失败时应抛出 PluginError。"""
        from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
            TencentCloudSDKException,
        )

        domain_resp = MagicMock()
        domain_resp.DomainList = [_make_domain(100, "example.com")]
        self.mock_sdk.DescribeDomainList.return_value = domain_resp
        self.mock_sdk.CreateRecord.side_effect = TencentCloudSDKException(
            "AuthFailure", "签名验证失败"
        )

        with self.assertRaises(errors.PluginError) as ctx:
            self.client.add_txt_record(
                "example.com", "_acme-challenge.example.com", "token"
            )
        self.assertIn("创建 TXT 记录失败", str(ctx.exception))

    # --- del_txt_record ---

    def test_del_txt_record_success(self):
        """正常删除匹配的 TXT 记录。"""
        domain_resp = MagicMock()
        domain_resp.DomainList = [_make_domain(100, "example.com")]
        self.mock_sdk.DescribeDomainList.return_value = domain_resp

        list_resp = MagicMock()
        list_resp.RecordList = [_make_record(555, "validation_token_123")]
        self.mock_sdk.DescribeRecordList.return_value = list_resp

        self.client.del_txt_record(
            "example.com",
            "_acme-challenge.example.com",
            "validation_token_123",
        )

        # 验证 DeleteRecord 被调用，RecordId 正确
        self.mock_sdk.DeleteRecord.assert_called_once()
        req = self.mock_sdk.DeleteRecord.call_args[0][0]
        self.assertEqual(req.RecordId, 555)

    def test_del_txt_record_only_matching_value(self):
        """只删除 value 匹配的记录，不误删其他 TXT 记录。"""
        domain_resp = MagicMock()
        domain_resp.DomainList = [_make_domain(100, "example.com")]
        self.mock_sdk.DescribeDomainList.return_value = domain_resp

        list_resp = MagicMock()
        list_resp.RecordList = [
            _make_record(111, "other_token"),           # 不应被删除
            _make_record(222, "validation_token_123"),  # 应被删除
        ]
        self.mock_sdk.DescribeRecordList.return_value = list_resp

        self.client.del_txt_record(
            "example.com",
            "_acme-challenge.example.com",
            "validation_token_123",
        )

        # 只调用了一次 DeleteRecord，且 RecordId 为 222
        self.mock_sdk.DeleteRecord.assert_called_once()
        req = self.mock_sdk.DeleteRecord.call_args[0][0]
        self.assertEqual(req.RecordId, 222)

    def test_del_txt_record_not_found(self):
        """找不到匹配记录时不报错，静默跳过。"""
        domain_resp = MagicMock()
        domain_resp.DomainList = [_make_domain(100, "example.com")]
        self.mock_sdk.DescribeDomainList.return_value = domain_resp

        list_resp = MagicMock()
        list_resp.RecordList = []
        self.mock_sdk.DescribeRecordList.return_value = list_resp

        # 不应抛出异常
        self.client.del_txt_record(
            "example.com", "_acme-challenge.example.com", "token"
        )
        self.mock_sdk.DeleteRecord.assert_not_called()


if __name__ == "__main__":
    unittest.main()
