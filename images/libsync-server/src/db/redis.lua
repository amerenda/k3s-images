local Gin = require 'gin.core.gin'

-- First, specify the environment settings for this database, for instance:
local DbSettings = {
    development = {
        host = "127.0.0.1",
        port = 6379,
        database = 3,
        pool = 5
    },

    test = {
        host = "127.0.0.1",
        port = 6379,
        database = 2,
        pool = 5
    },

    -- host/port/database/password are overridable via env vars so this image
    -- can point at an external Redis instance instead of the bundled one
    -- upstream normally runs in-container. Defaults match upstream.
    production = {
        host = os.getenv("REDIS_HOST") or "127.0.0.1",
        port = tonumber(os.getenv("REDIS_PORT")) or 6379,
        database = tonumber(os.getenv("REDIS_DB")) or 1,
        pool = 5,
        password = os.getenv("REDIS_PASSWORD"),
    }
}

-- Then initialize and return your database:
local Redis = {
    options = {},
}

function Redis:new()
    local redis = require("resty.redis")
    local option = DbSettings[Gin.env]
    local red = redis:new()
    red:set_timeout(1000) -- 1 sec
    local ok, err = red:connect(option.host, option.port)
    if ok then
        if option.password and option.password ~= "" then
            local auth_ok, auth_err = red:auth(option.password)
            if not auth_ok then
                return nil
            end
        end
        red:select(option.database)
        return red
    end
end

return Redis
