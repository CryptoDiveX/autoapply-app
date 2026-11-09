# Common Ninja hosted careers shell

1. Follow the employer's observed Careers link. A guest-contributor form is not a paid job.
2. Before fetching shared JavaScript bundles, decode public `script#__NEXT_DATA__` offline. Candidate-visible page text can be retained under `props.pageProps.pluginData.data.content.elements` even when the HTML body says JavaScript is required.
3. Whitelist text, title, label, description and observed public links from that content tree. Exclude configuration and unrelated editor, account, subscription and administrative components. Do not fetch every shared bundle or print API configuration.
4. Preserve the official employer-to-careers link, HTTP status, final URL, timestamp and original HTML. An explicit no-open-positions notice in this exact published careers content means no currently advertised named vacancy on that page. A `published` widget status establishes page publication, not vacancy availability.
5. If bundle-first inspection was unnecessarily broad, preserve its request metadata, report the excessive public retrieval workload honestly, and recover only the offline content projection. Do not promote research, infer company country or create a hypothetical tracker record.
