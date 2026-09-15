import Foundation

// 跨服務共用的基礎設施型別(非業務實體,不受微服務邊界規則約束)。

struct Page<T: Codable>: Codable {
    let items: [T]
    let nextCursor: String?
}
