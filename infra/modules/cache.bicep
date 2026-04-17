// cache.bicep - Azure Cache for Redis

@description('Name prefix for Redis cache')
param namePrefix string

@description('Azure region for resource deployment')
param location string

@description('Resource tags')
param tags object = {}

resource redisCache 'Microsoft.Cache/redis@2023-08-01' = {
  name: '${namePrefix}-redis'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'Basic'
      family: 'C'
      capacity: 0
    }
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
    redisConfiguration: {
      'maxmemory-policy': 'allkeys-lru'
    }
  }
}

output redisCacheId string = redisCache.id
output redisCacheName string = redisCache.name
output redisHostName string = redisCache.properties.hostName
output redisSslPort int = redisCache.properties.sslPort
output redisAccessKey string = redisCache.listKeys().primaryKey
