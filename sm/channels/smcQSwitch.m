function val = smcQSwitch(ic, val, rate)
% smcQSwitch  Special Measure adapter for the single-owner Python controller.
% Selectors remain OPEN, CLOSE, STATE, IDENTITY, ERROR, RESET. OPEN/CLOSE
% values are an N-by-2 [signal_line destination] matrix.
global smdata;
if numel(ic) < 3 || any(~isfinite(ic(1:3))) || any(ic(1:3) ~= fix(ic(1:3)))
    error('smcQSwitch:InvalidChannel', 'ic must contain integer instrument, channel, and operation indices.');
end
inst = smdata.inst(ic(1)).data;
if ~isfield(inst, 'controller_url') || isempty(inst.controller_url)
    error('smcQSwitch:Configuration', 'QSwitch controller_url is not configured.');
end
channel = ic(2); operation = ic(3); %#ok<NASGU>
options = weboptions('MediaType', 'application/json', 'Timeout', 10);
switch channel
    case 1
        require_write(operation, 'OPEN'); val = relay_request(inst.controller_url, 'open', val, options);
    case 2
        require_write(operation, 'CLOSE'); val = relay_request(inst.controller_url, 'close', val, options);
    case 3
        require_read(operation, 'STATE'); snapshot = webread([inst.controller_url '/state'], options); val = state_text(snapshot.state);
    case 4
        require_read(operation, 'IDENTITY'); response = webread([inst.controller_url '/identity'], options); val = response.identity;
    case 5
        require_read(operation, 'ERROR'); response = webread([inst.controller_url '/error'], options); val = response.error;
    case 6
        require_write(operation, 'RESET'); webwrite([inst.controller_url '/reset'], struct('actor', 'automation'), options);
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
                any(addresses(:,1) < 1 | addresses(:,1) > 24) || any(addresses(:,2) < 0 | addresses(:,2) > 9)
            error('smcQSwitch:InvalidRelayAddress', 'Signal lines must be integers 1..24 and destinations 0..9.');
        end
        response = [];
        for n = 1:size(addresses,1)
            payload = struct('signal', addresses(n,1), 'destination', addresses(n,2), 'actor', 'automation');
            response = webwrite([base '/relays/' action], payload, opts); %#ok<AGROW>
        end
    end

    function text = state_text(entries)
        if isempty(entries), text = '(@)'; return; end
        parts = cell(numel(entries),1);
        for n = 1:numel(entries), parts{n} = entries{n}; end
        text = ['(@' strjoin(parts, ',') ')'];
    end
    function require_read(op, name)
        if op ~= 0, error('smcQSwitch:OperationNotSupported', '%s is read-only.', name); end
    end
    function require_write(op, name)
        if op ~= 1, error('smcQSwitch:OperationNotSupported', '%s is write-only.', name); end
    end
end
