// 跨服務共用的基礎設施型別(非業務實體,不受微服務邊界規則約束)。
// 純粹的分頁信封,任何服務的分頁 API 都可以用同一個泛型,不需要每個服務各自定義一份。

export interface Page<T> {
  items: T[];
  nextCursor: string | null;
}
