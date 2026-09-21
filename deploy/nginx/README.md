# Nginx 閘道設定

規格見 [`rule_doc/功能需求/14_API閘道與路由規範.md`](../../rule_doc/功能需求/14_API閘道與路由規範.md),本目錄的設定必須與它一致。

使用官方 `nginx` 映像,以 `network_mode: host` 執行。`*.template` 由映像啟動時的 envsubst 產生到 `/etc/nginx/conf.d/`。映像內建的 `/etc/nginx/conf.d/default.conf` 會在主機上多開 port 80,必須以空檔案覆蓋或刪除。port 配置見規範第 2 節。

## VM-1 / VM-2

| 本目錄 | 容器內路徑 |
|---|---|
| `shared/proxy_params.conf` | `/etc/nginx/pet_camera/proxy_params.conf` |
| `shared/errors.conf` | `/etc/nginx/pet_camera/errors.conf` |
| `shared/internal.conf` | `/etc/nginx/conf.d/internal.conf` |
| `service-node/public.conf` | `/etc/nginx/conf.d/public.conf` |
| `service-node/upstreams.conf.template` | `/etc/nginx/templates/upstreams.conf.template` |
| `service-node/real_ip.conf.template` | `/etc/nginx/templates/real_ip.conf.template` |

| 環境變數 | VM-1 | VM-2 |
|---|---|---|
| `PEER_HOST` | `vm2.internal` | `vm1.internal` |
| `LB_SUBNET_CIDR` | LB 子網路 CIDR | LB 子網路 CIDR |

## VM-3

| 本目錄 | 容器內路徑 |
|---|---|
| `shared/proxy_params.conf` | `/etc/nginx/pet_camera/proxy_params.conf` |
| `shared/errors.conf` | `/etc/nginx/pet_camera/errors.conf` |
| `shared/internal.conf` | `/etc/nginx/conf.d/internal.conf` |
| `singleton-node/upstreams.conf` | `/etc/nginx/conf.d/upstreams.conf` |

VM-3 不需要環境變數,也不放 `public.conf`。
