process SAMPLESHEETPARSER_FILTER {
    tag "$meta.id"
    label 'process_single'

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container ?
        'https://depot.galaxyproject.org/singularity/samplesheet-parser:1.2.0--pyhdfd78af_0' :
        'biocontainers/samplesheet-parser:1.2.0--pyhdfd78af_0' }"

    input:
    tuple val(meta), path(samplesheet)

    output:
    tuple val(meta), path("*.filtered.csv"), emit: samplesheet, optional: true
    tuple val(meta), path("*.filter.json"),  emit: json
    path "versions.yml",                     emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def args   = task.ext.args   ?: ''
    def prefix = task.ext.prefix ?: "${meta.id}"
    """
    samplesheet filter \\
        --output ${prefix}.filtered.csv \\
        --format json \\
        ${args} \\
        ${samplesheet} > ${prefix}.filter.json || true

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        samplesheet-parser: \$(samplesheet --version | sed 's/samplesheet-parser //')
    END_VERSIONS
    """

    stub:
    def prefix = task.ext.prefix ?: "${meta.id}"
    """
    touch ${prefix}.filtered.csv
    echo '{"matched_count": 0, "total_count": 0, "output_path": null, "criteria": {}}' > ${prefix}.filter.json

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        samplesheet-parser: \$(samplesheet --version | sed 's/samplesheet-parser //')
    END_VERSIONS
    """
}
