package com.petcamera.interfaces

// 跨服務共用的基礎設施型別(非業務實體,不受微服務邊界規則約束)。

data class Page<T>(
    val items: List<T>,
    val nextCursor: String?,
)
