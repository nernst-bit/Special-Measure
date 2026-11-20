function val = smcQSwitch(ic, val, rate)
% smcQSwitch  Special Measure adapter for a group-scoped QSwitch controller.
% Selectors include OPEN, CLOSE, STATE, IDENTITY, ERROR, RESET, ACQUIRE,
% RELEASE, CONFIGS, RESTORE. OPEN/CLOSE
% values are N-by-2 [fridge_line system_BNC] route intents.
% Ground (destination 0) and IN (destination 9) relay mutations are rejected;
% the centralized controller derives and sequences those relays from routes.
global smdata;
if numel(ic) < 3 || any(~isfinite(ic(1:3))) || any(ic(1:3) ~= fix(ic(1:3)))
    error('smcQSwitch:InvalidChannel', 'ic must contain integer instrument, channel, and operation indices.');
end
inst = smdata.inst(ic(1)).data;
if ~isfield(inst, 'controller_url') || isempty(inst.controller_url)
    error('smcQSwitch:Configuration', 'QSwitch controller_url is not configured.');
end
if ~isfield(inst, 'group_id') || isempty(inst.group_id), inst.group_id = 'default'; end
groupQuery = ['?group_id=' char(string(inst.group_id))];
channel = ic(2); operation = ic(3); %#ok<NASGU>
options = weboptions('MediaType', 'application/json', 'Timeout', 10);
switch channel
    case 1
        require_write(operation, 'OPEN'); relay_request(inst.controller_url, 'open', val, options);
    case 2
        require_write(operation, 'CLOSE'); relay_request(inst.controller_url, 'close', val, options);
    case 3
        require_read(operation, 'STATE'); snapshot = webread([inst.controller_url '/state' groupQuery], options); val = state_text(snapshot.state);
    case 4
        require_read(operation, 'IDENTITY'); response = webread([inst.controller_url '/identity' groupQuery], options); val = response.identity;
    case 5
        require_read(operation, 'ERROR'); response = webread([inst.controller_url '/error' groupQuery], options); val = response.error;
    case 6
        require_write(operation, 'RESET');
        payload = struct('actor', 'automation', 'group_id', inst.group_id, ...
            'ownership_token', inst.ownership_token);
        webwrite([inst.controller_url '/reset'], payload, options);
    case 7
        require_write(operation, 'ACQUIRE');
        response = webwrite([inst.controller_url '/measurement/acquire'], struct('owner', 'Special Measure', 'group_id', inst.group_id), options);
        smdata.inst(ic(1)).data.ownership_token = response.token;
        val = response.status;
    case 8
        require_write(operation, 'RELEASE');
        if ~isfield(inst, 'ownership_token') || isempty(inst.ownership_token)
            error('smcQSwitch:Ownership', 'This Special Measure instrument has no active ownership token.');
        end
        response = webwrite([inst.controller_url '/measurement/release'], struct('token', inst.ownership_token, 'group_id', inst.group_id), options);
        smdata.inst(ic(1)).data.ownership_token = '';
        val = response.status;
    case 9
        require_read(operation, 'CONFIGS');
        response = webread([inst.controller_url '/configurations' groupQuery], options);
        val = configuration_names(response);
    case 10
        require_write(operation, 'RESTORE');
        configurationName = char(string(val));
        if isempty(strtrim(configurationName))
            error('smcQSwitch:ConfigurationName', 'Select a saved QSwitch configuration to restore.');
        end
        if ~isfield(inst, 'ownership_token') || isempty(inst.ownership_token)
            error('smcQSwitch:Ownership', 'Acquire measurement ownership before restoring a QSwitch configuration.');
        end
        payload = struct('name', configurationName, 'group_id', inst.group_id, ...
            'actor', 'automation', 'ownership_token', inst.ownership_token);
        val = webwrite([inst.controller_url '/configurations/restore'], payload, options);
    otherwise
        error('smcQSwitch:InvalidChannel', 'Unsupported QSwitch channel %d.', channel);
end
if nargin >= 3 && ~isempty(rate) %#ok<INUSD>
    % Discrete controller operations accept rate for Special Measure compatibility.
end

    function response = relay_request(base, action, addresses, opts)
        if ~isnumeric(addresses) || isempty(addresses) || ndims(addresses) ~= 2 || size(addresses,2) ~= 2
            error('smcQSwitch:InvalidRelayAddress', 'Relay address must be a nonempty N-by-2 numeric array.');
        end
        if any(~isfinite(addresses(:))) || any(addresses(:) ~= fix(addresses(:))) || ...
                any(addresses(:,1) < 1 | addresses(:,1) > 24) || any(addresses(:,2) < 1)
            error('smcQSwitch:InvalidRelayAddress', 'Fridge lines must be integers 1..24 and system BNC numbers positive integers.');
        end
        routes = cell(size(addresses, 1), 1);
        for n = 1:size(addresses,1)
            routes{n} = struct('signal', addresses(n,1), 'bnc', addresses(n,2));
        end
        payload = struct('routes', {routes}, 'actor', 'automation', 'group_id', inst.group_id);
        if isfield(inst, 'ownership_token') && ~isempty(inst.ownership_token)
            payload.ownership_token = inst.ownership_token;
        end
        % The controller derives IN/Ground dependencies and verifies each step.
        response = webwrite([base '/routes/batch/' route_action(action)], payload, opts);
    end

    function text = state_text(entries)
        if isempty(entries), text = '(@)'; return; end
        parts = cell(numel(entries),1);
        for n = 1:numel(entries), parts{n} = entries{n}; end
        text = ['(@' strjoin(parts, ',') ')'];
    end
    function names = configuration_names(response)
        names = {};
        if ~isfield(response, 'configurations') || isempty(response.configurations), return; end
        configurations = response.configurations;
        if iscell(configurations), configurations = [configurations{:}]; end
        names = cell(1, numel(configurations));
        for n = 1:numel(configurations)
            names{n} = char(string(configurations(n).name));
        end
    end
    function action_name = route_action(relay_action)
        if strcmp(relay_action, 'close'), action_name = 'connect'; else, action_name = 'disconnect'; end
    end
    function require_read(op, name)
        if op ~= 0, error('smcQSwitch:OperationNotSupported', '%s is read-only.', name); end
    end
    function require_write(op, name)
        if op ~= 1, error('smcQSwitch:OperationNotSupported', '%s is write-only.', name); end
    end
end
