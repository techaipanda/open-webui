"""
搜狗搜索模块
功能: 使用腾讯云搜狗搜索 API 进行网络搜索

概述:
搜狗搜索是腾讯云提供的搜索服务，基于搜狗搜索引擎。
本模块使用腾讯云 SDK 进行接口调用。

特点:
- 使用腾讯云认证体系
- 支持相关性排序
- 返回标题、URL 和摘要

环境变量:
- SOGOU_API_SID: 腾讯云账户 SID
- SOGOU_API_SK: 腾讯云账户 SK
"""

import logging
import json
from typing import Optional, List


from open_webui.retrieval.web.main import SearchResult, get_filtered_results

log = logging.getLogger(__name__)


def search_sougou(
    sougou_api_sid: str,
    sougou_api_sk: str,
    query: str,
    count: int,
    filter_list: Optional[List[str]] = None,
) -> List[SearchResult]:
    """
    使用搜狗搜索 API 搜索并返回结果

    Args:
        sougou_api_sid: 腾讯云账户 SID
        sougou_api_sk: 腾讯云账户 SK
        query: 搜索查询字符串
        count: 返回结果数量
        filter_list: 可选的域名过滤列表

    Returns:
        SearchResult 对象列表
    """
    from tencentcloud.common.common_client import CommonClient
    from tencentcloud.common import credential
    from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
        TencentCloudSDKException,
    )
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile

    try:
        cred = credential.Credential(sougou_api_sid, sougou_api_sk)
        http_profile = HttpProfile()
        http_profile.endpoint = 'tms.tencentcloudapi.com'
        client_profile = ClientProfile()
        client_profile.http_profile = http_profile
        params = json.dumps({'Query': query, 'Cnt': 20})
        common_client = CommonClient('tms', '2020-12-29', cred, '', profile=client_profile)
        results = [
            json.loads(page) for page in common_client.call_json('SearchPro', json.loads(params))['Response']['Pages']
        ]
        sorted_results = sorted(results, key=lambda x: x.get('scour', 0.0), reverse=True)
        if filter_list:
            sorted_results = get_filtered_results(sorted_results, filter_list)

        return [
            SearchResult(
                link=result.get('url'),
                title=result.get('title'),
                snippet=result.get('passage'),
            )
            for result in sorted_results[:count]
        ]
    except TencentCloudSDKException as err:
        log.error(f'Error in Sougou search: {err}')
        return []